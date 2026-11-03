"""自定义策略脚本加载器。

策略脚本放在 `backend/strategies/*.py`，由本模块按需加载：

    NAME = "双均线交叉"            # 显示名，缺省用文件名
    DESCRIPTION = "……"             # 一句话说明
    PARAMS = [                     # 参数声明，前端据此生成表单
        {"name": "fast", "label": "快线周期", "default": 5, "min": 1, "max": 500},
    ]

    def build(params):             # params 已按声明做过类型转换与范围校验
        return SG_Cross(MA(CLOSE(), n=params["fast"]), ...)

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


@dataclass
class StrategyInfo:
    id: str
    name: str
    description: str
    params: list[StrategyParam] = field(default_factory=list)
    error: str | None = None


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
            )
        )
    return out


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


def build_signal(strategy_id: str, params: dict[str, Any] | None = None):
    """执行策略脚本的 build(params)，返回 hikyuu 的 SG 实例。"""
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
        # 整数型参数（default 是 int）保留 int，避免 MA(n=5.0) 之类的问题
        resolved[definition.name] = (
            int(value) if isinstance(definition.default, int) and not isinstance(definition.default, bool) else value
        )

    try:
        signal = build(resolved)
    except Exception as exc:  # noqa: BLE001 - 用户脚本
        raise StrategyError(
            f"策略 {strategy_id} 执行失败：{type(exc).__name__}: {exc}"
        ) from exc
    if signal is None:
        raise StrategyError(f"策略 {strategy_id} 的 build() 返回了 None")
    return signal
