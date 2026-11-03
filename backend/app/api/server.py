"""FastAPI 应用与作业队列。

自用工具场景，回测耗时约 0.006s，因此用内存作业表 + 线程池即可，
不需要 Celery / Redis。实测 6 个回测并发执行结果一致，线程安全。
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.schemas import (
    BacktestRequest,
    HealthResponse,
    JobCreated,
    MoneyRequest,
    OverlayQueryRequest,
    OverlayRequest,
    StrategyRequest,
    SymbolInfo,
)
from app.config import HIKYUU_INI, write_hikyuu_ini
from app.core.engine import (
    COST_MODEL_LABELS,
    BacktestSpec,
    EngineError,
    MoneySpec,
    OverlaySpec,
    StrategySpec,
    build_query,
    extract_overlays,
    get_stock,
    load_hikyuu,
    require_kdata,
    run_backtest,
)
from app.data import catalog
from app.data.bootstrap import registered_symbols, seed_symbol

app = FastAPI(title="Hikyuu 回测 API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 作业管理 ---
# 只保留最近若干条：每个结果都带着整段 K 线 / 资金曲线，长期运行不清理会一直涨内存
MAX_JOBS = 50
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="backtest")

# Hikyuu 的 StockManager 是全局单例，共享一份可避免重复加载数据
_sm = None
_sm_lock = threading.Lock()

# 引擎状态机：idle（未加载）→ loading（加载中）→ ready（就绪）/ error（加载失败）
# 前端据此轮询 /api/health，实时反映引擎状态
_engine_state = "idle"
_engine_error: str | None = None


def _get_stock_manager():
    """懒加载 StockManager（首次调用时读 HDF5，约 0.01s）。"""
    global _sm, _engine_state, _engine_error
    with _sm_lock:
        if _sm is None:
            _engine_state = "loading"
            _engine_error = None
            try:
                ini = write_hikyuu_ini()
                symbols = [s["symbol"] for s in registered_symbols()]
                # 交易日历依赖市场主指数，必须一并加载
                for code in ("sh000001", "sh000300"):
                    if code not in symbols:
                        symbols.append(code)
                _sm = load_hikyuu(str(ini), symbols)
            except Exception as exc:  # noqa: BLE001
                # 加载失败时保留错误信息，供 /api/health 上报，前端可见
                _engine_state = "error"
                _engine_error = f"{type(exc).__name__}: {exc}"
                raise
            else:
                _engine_state = "ready"
        return _sm


def _run_job(job_id: str, spec: BacktestSpec) -> None:
    try:
        with _jobs_lock:
            _jobs[job_id]["status"] = "running"
            _jobs[job_id]["started_at"] = time.time()

        sm = _get_stock_manager()
        result = run_backtest(sm, spec)

        with _jobs_lock:
            _jobs[job_id].update(
                status="done",
                result=result,
                finished_at=time.time(),
            )
    except EngineError as exc:
        with _jobs_lock:
            _jobs[job_id].update(
                status="error", error=str(exc), finished_at=time.time()
            )
    except Exception as exc:  # noqa: BLE001
        with _jobs_lock:
            _jobs[job_id].update(
                status="error",
                error=f"{type(exc).__name__}: {exc}",
                traceback=traceback.format_exc(),
                finished_at=time.time(),
            )


@app.post("/api/backtests", response_model=JobCreated)
def create_backtest(request: BacktestRequest) -> JobCreated:
    """提交回测任务，立即返回 job id，结果通过轮询获取。"""
    job_id = uuid.uuid4().hex[:12]
    spec = BacktestSpec(
        symbol=request.symbol.lower(),
        start=request.start,
        end=request.end,
        init_cash=request.init_cash,
        cost_model=request.cost_model,
        money=MoneySpec(
            type=request.money.type,
            n=request.money.n,
            percent=request.money.percent,
        ),
        strategy=StrategySpec(id=request.strategy.id, params=dict(request.strategy.params)),
        overlays=[
            OverlaySpec(type=o.type, n=o.n, key=o.key) for o in request.overlays
        ],
        stoploss=request.stoploss,
        takeprofit=request.takeprofit,
        slippage=request.slippage,
    )

    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id,
            "status": "queued",
            "created_at": time.time(),
            "request": request.model_dump(),
        }
        while len(_jobs) > MAX_JOBS:
            # dict 保持插入顺序，最早创建的先淘汰；正在跑的也不淘汰
            oldest = next(
                (k for k, v in _jobs.items() if v["status"] not in ("queued", "running")),
                None,
            )
            if oldest is None:
                break
            _jobs.pop(oldest, None)

    _pool.submit(_run_job, job_id, spec)
    return JobCreated(id=job_id, status="queued")


@app.get("/api/backtests/{job_id}")
def get_backtest(job_id: str) -> dict[str, Any]:
    """查询回测状态与结果。"""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


@app.get("/api/symbols", response_model=list[SymbolInfo])
def list_symbols() -> list[SymbolInfo]:
    """本地已导入的标的清单。"""
    out = []
    for entry in catalog.list_all():
        out.append(
            SymbolInfo(
                symbol=entry["symbol"],
                market=entry["market"],
                code=entry["code"],
                name=entry["name"],
                kind=entry["kind"],
                last_date=entry.get("last_date"),
            )
        )
    return out


# 看护脚本：等本进程退出后重新拉起 uvicorn。参数依次为端口、host、工作目录、等待秒数。
_WATCHDOG = """
import socket, subprocess, sys, time
port, host, cwd, wait = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])
time.sleep(wait)


def port_free() -> bool:
    with socket.socket() as sock:
        sock.settimeout(1.0)
        # connect_ex 返回 0 表示还有人监听，端口未释放
        return sock.connect_ex((host, int(port))) != 0


# 等到旧进程真正退出、端口释放后再启动；若被其它进程（如 --reload 的看护）
# 抢先占用，则放弃本次启动，避免两个服务抢同一个端口
for _ in range(50):
    if port_free():
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.api.server:app", "--host", host, "--port", port],
            cwd=cwd,
        )
        break
    time.sleep(0.2)
"""


def _schedule_restart(port: int, host: str, delay: float = 1.5) -> None:
    """本次响应发出后重启服务，让 Hikyuu 重新读取行情。

    Hikyuu 的 StockManager 一旦 load 就不会重新读盘（实测 reload() 无效），
    只有进程重启才会加载刷新后的数据。这里拉起一个看护进程，
    等本进程退出、端口释放后再启动新的 uvicorn。
    """
    if os.environ.get("HK_NO_AUTO_RESTART"):
        return

    backend_dir = Path(__file__).resolve().parents[2]

    def _restart() -> None:
        time.sleep(0.2)
        subprocess.Popen(
            [sys.executable, "-c", _WATCHDOG, str(port), host, str(backend_dir), str(delay)],
            cwd=str(backend_dir),
            close_fds=True,
        )
        os._exit(0)

    threading.Thread(target=_restart, daemon=True).start()


@app.post("/api/symbols/refresh")
def refresh_symbols(request: Request) -> dict[str, Any]:
    """增量更新所有已导入标的的行情数据。完成后自动重启服务以加载新数据。"""
    entries = catalog.list_all()
    results = []
    for entry in entries:
        result = seed_symbol(
            entry["market"],
            entry["code"],
            entry["name"],
            entry["kind"],
            incremental=True,
        )
        results.append(
            {
                "symbol": result.symbol,
                "rows": result.rows,
                "status": "error" if result.error else ("skipped" if result.skipped else "ok"),
                "error": result.error,
            }
        )

    updated = sum(1 for r in results if r["status"] == "ok")
    if updated and entries:
        # 端口取自本次请求：服务可能不在默认的 8000 上
        port = request.url.port or (443 if request.url.scheme == "https" else 80)
        _schedule_restart(port, request.url.hostname or "127.0.0.1")

    return {
        "refreshed": len(results),
        "updated": updated,
        "restarting": bool(updated),
        "results": results,
    }


@app.post("/api/overlays")
def compute_overlays(request: OverlayQueryRequest) -> dict[str, list[float]]:
    """只计算指标叠加线，不跑回测。

    前端勾选指标后调用本接口重画叠加线，避免为了换指标重跑整个回测。
    指标值与回测结果里的完全一致（同一套 extract_overlays）。
    """
    sm = _get_stock_manager()
    symbol = request.symbol.lower()
    query = build_query(request.start, request.end)
    specs = [OverlaySpec(type=o.type, n=o.n, key=o.key) for o in request.overlays]
    try:
        stock = get_stock(sm, symbol)
        kdata = require_kdata(stock, query, symbol, request.start, request.end)
        return extract_overlays(kdata, specs)
    except EngineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - 其它引擎内部异常也返回可读信息
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}") from exc


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """引擎状态。

    引擎在首次回测时懒加载，因此这里上报的是实时状态，
    前端轮询本接口即可看到引擎由「待加载」变为「就绪」。
    """
    available = catalog.list_all()
    ready = _sm is not None
    loaded = 0
    if ready and _sm is not None:
        loaded = len(list(_sm))
    if ready:
        detail = None
    elif _engine_state == "error":
        detail = _engine_error or "引擎加载失败"
    else:
        detail = "引擎尚未加载，首次回测时会自动初始化"
    return HealthResponse(
        status="ok" if _engine_state != "error" else "error",
        engine_state="ready" if ready else _engine_state,
        engine_ready=ready,
        loaded_symbols=loaded,
        available_symbols=len(available),
        cost_models=COST_MODEL_LABELS,
        detail=detail,
    )


@app.get("/api/strategies")
def list_strategies() -> list[dict[str, Any]]:
    """自定义策略脚本清单（backend/strategies/*.py）。

    脚本导入失败时对应项带 error 字段，不影响其它策略。
    """
    from dataclasses import asdict

    from app.core.strategy_loader import list_strategies as _list

    return [asdict(s) for s in _list()]


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    """前端初始化需要的元信息。"""
    return {
        "cost_models": COST_MODEL_LABELS,
        "default_symbol": "sh510300",
        "default_overlays": [
            {"type": "ma", "n": 5},
            {"type": "ma", "n": 20},
        ],
    }
