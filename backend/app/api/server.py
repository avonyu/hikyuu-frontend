"""FastAPI 应用与作业队列。

自用工具场景，回测耗时约 0.006s，因此用内存作业表 + 线程池即可，
不需要 Celery / Redis。实测 6 个回测并发执行结果一致，线程安全。
"""
from __future__ import annotations

import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api.schemas import (
    BacktestRequest,
    HealthResponse,
    JobCreated,
    MoneyRequest,
    OverlayRequest,
    SignalRequest,
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
    SignalSpec,
    StrategySpec,
    load_hikyuu,
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
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="backtest")

# Hikyuu 的 StockManager 是全局单例，共享一份可避免重复加载数据
_sm = None
_sm_lock = threading.Lock()


def _get_stock_manager():
    """懒加载 StockManager（首次调用时读 HDF5，约 0.01s）。"""
    global _sm
    with _sm_lock:
        if _sm is None:
            ini = write_hikyuu_ini()
            symbols = [s["symbol"] for s in registered_symbols()]
            # 交易日历依赖市场主指数，必须一并加载
            for code in ("sh000001", "sh000300"):
                if code not in symbols:
                    symbols.append(code)
            _sm = load_hikyuu(str(ini), symbols)
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
        signal=SignalSpec(
            type=request.signal.type,
            fast=request.signal.fast,
            slow=request.signal.slow,
            n=request.signal.n,
        ),
        money=MoneySpec(
            type=request.money.type,
            n=request.money.n,
            percent=request.money.percent,
        ),
        strategy=(
            StrategySpec(id=request.strategy.id, params=dict(request.strategy.params))
            if request.strategy
            else None
        ),
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


@app.post("/api/symbols/refresh")
def refresh_symbols() -> dict[str, Any]:
    """增量更新所有已导入标的的行情数据。"""
    results = []
    for entry in catalog.list_all():
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
    return {"refreshed": len(results), "results": results}


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """引擎状态。"""
    available = catalog.list_all()
    ready = _sm is not None
    loaded = 0
    if ready and _sm is not None:
        loaded = len(list(_sm))
    return HealthResponse(
        status="ok",
        engine_ready=ready,
        loaded_symbols=loaded,
        available_symbols=len(available),
        cost_models=COST_MODEL_LABELS,
        detail=None if ready else "引擎尚未加载，首次回测时会自动初始化",
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
