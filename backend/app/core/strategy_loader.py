"""自定义策略脚本加载器。

策略脚本放在 `backend/strategies/*.py`，由本模块按需加载：

    NAME = "双均线交叉"            # 显示名，缺省用文件名
    DESCRIPTION = "……"             # 一句话说明
    PARAMS = [                     # 参数声明，前端据此生成表单
        {"name": "fast", "label": "快线周期", "default": 5, "min": 1, "max": 500},
    ]

    def build(params):             # params 已按声明做过类型转换与范围校验
        return SG_Cross(MA(CLOSE(), n=params["fast"]), ...)

build() 可以只返回一个信号发生器（只用信号，资金管理与风控由表单控制），
也可以返回字典，连同自己的资金管理 / 目标价一起交给引擎：

    def build(params):
        return {"sg": sg, "mm": mm}     # mm 可选，pg / tp 同理

- 模块按文件 mtime 缓存，改脚本后下一次回测即生效，无需重启服务；
- 脚本在服务进程内执行（等价于给本机开了一个代码执行入口），只放自己信任的代码；
- 单个脚本导入失败不影响其它策略，错误会随 /api/strategies 一起返回。
"""
from __future__ import annotations

import importlib.util
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

STRATEGY_DIR = Path(
    os.environ.get(
        "HK_STRATEGY_DIR",
        Path(__file__).resolve().parents[2] / "strategies",  # backend/strategies
    )
)


class StrategyError(RuntimeError):
    """策略不存在、加载失败或参数非法。"""


@dataclass
class StrategyParam:
    name: str
    label: str
    default: float | int
    min: float | None = None
    max: float | None = None
    # 由 default 的类型决定：default 写成 int 即整数参数，写成 float（如 2.0）即小数参数
    integer: bool = False


@dataclass
class StrategyInfo:
    id: str
    name: str
    description: str
    params: list[StrategyParam] = field(default_factory=list)
    error: str | None = None
    # 脚本自带资金管理（表单里的「资金管理」设置对它不生效）
    money_manager: bool = False


@dataclass
class StrategyParts:
    """策略脚本产出的交易系统组件。"""

    sg: Any                                  # 信号发生器，必需
    mm: Any = None                           # 资金管理，可选
    pg: Any = None                           # 目标价（止盈），可选
    tp: Any = None                           # 移动止盈，可选


_loaded: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()


def _script_paths() -> list[Path]:
    if not STRATEGY_DIR.is_dir():
        return []
    return sorted(
        p for p in STRATEGY_DIR.glob("*.py") if not p.name.startswith("_")
    )


def _module_for(path: Path):
    """按 mtime 缓存加载模块；文件变了就重新执行。"""
    mtime = path.stat().st_mtime
    key = str(path)
    with _lock:
        cached = _loaded.get(key)
        if cached and cached[0] == mtime:
            return cached[1]

        name = f"hk_strategy_{path.stem}_{int(mtime)}"
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise StrategyError(f"无法加载策略脚本 {path.name}")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:  # noqa: BLE001 - 用户脚本里的任意错误
            raise StrategyError(
                f"加载 {path.name} 失败：{type(exc).__name__}: {exc}"
            ) from exc
        _loaded[key] = (mtime, module)
        return module


def _param_defs(module) -> list[StrategyParam]:
    raw = getattr(module, "PARAMS", []) or []
    out: list[StrategyParam] = []
    for item in raw:
        name = str(item.get("name", "")).strip()
        if not name:
            raise StrategyError("PARAMS 里有一项缺少 name")
        out.append(
            StrategyParam(
                name=name,
                label=str(item.get("label", name)),
                default=item.get("default", 0),
                min=item.get("min"),
                max=item.get("max"),
                integer=_is_int(item.get("default", 0)),
            )
        )
    return out


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def list_strategies() -> list[StrategyInfo]:
    """扫描策略目录；单个脚本出错只标记该条，不影响整体。"""
    out: list[StrategyInfo] = []
    for path in _script_paths():
        sid = path.stem
        try:
            module = _module_for(path)
            out.append(
                StrategyInfo(
                    id=sid,
                    name=str(getattr(module, "NAME", sid)),
                    description=str(getattr(module, "DESCRIPTION", "")),
                    params=_param_defs(module),
                    money_manager=bool(getattr(module, "MONEY_MANAGER", False)),
                )
            )
        except Exception as exc:  # noqa: BLE001
            out.append(
                StrategyInfo(
                    id=sid, name=sid, description="", error=f"{type(exc).__name__}: {exc}"
                )
            )
    return out


def _resolve_path(strategy_id: str) -> Path:
    """只允许 strategies 目录下的 <id>.py，挡掉路径穿越。"""
    sid = (strategy_id or "").strip()
    if not sid or Path(sid).name != sid:
        raise StrategyError(f"非法策略 id：{strategy_id!r}")
    path = STRATEGY_DIR / f"{sid}.py"
    if not path.is_file():
        raise StrategyError(f"策略不存在：{sid}")
    return path


def build_parts(strategy_id: str, params: dict[str, Any] | None = None) -> StrategyParts:
    """执行策略脚本的 build(params)，返回交易系统组件。

    build() 有两种返回形式：

    - 一个信号发生器（SG_*）：只用信号，资金管理与风控仍由表单控制；
    - 一个字典：``{"sg": ..., "mm": ..., "pg": ..., "tp": ...}``，
      其中 mm / pg / tp 可选，用于「定期定投」这类需要自己控制下单金额的策略。
    """
    path = _resolve_path(strategy_id)
    module = _module_for(path)

    build = getattr(module, "build", None)
    if not callable(build):
        raise StrategyError(f"{path.name} 缺少 build(params) 函数")

    provided = params or {}
    resolved: dict[str, Any] = {}
    for definition in _param_defs(module):
        raw = provided.get(definition.name, definition.default)
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise StrategyError(
                f"参数 {definition.name} 不是数字：{raw!r}"
            ) from exc
        if definition.min is not None and value < definition.min:
            raise StrategyError(f"参数 {definition.name} 不能小于 {definition.min}")
        if definition.max is not None and value > definition.max:
            raise StrategyError(f"参数 {definition.name} 不能大于 {definition.max}")
        # 整数型参数（default 是 int）转成 int，避免 MA(n=5.0) 之类的问题；小数参数原样保留
        resolved[definition.name] = int(value) if definition.integer else value

    try:
        result = build(resolved)
    except Exception as exc:  # noqa: BLE001 - 用户脚本
        raise StrategyError(
            f"策略 {strategy_id} 执行失败：{type(exc).__name__}: {exc}"
        ) from exc

    if result is None:
        raise StrategyError(f"策略 {strategy_id} 的 build() 返回了 None")

    if isinstance(result, dict):
        sg = result.get("sg")
        if sg is None:
            raise StrategyError(f"策略 {strategy_id} 返回的字典里缺少 sg")
        return StrategyParts(
            sg=sg,
            mm=result.get("mm"),
            pg=result.get("pg"),
            tp=result.get("tp"),
        )

    return StrategyParts(sg=result)


def build_signal(strategy_id: str, params: dict[str, Any] | None = None):
    """执行策略脚本的 build(params)，只取信号发生器。"""
    return build_parts(strategy_id, params).sg
