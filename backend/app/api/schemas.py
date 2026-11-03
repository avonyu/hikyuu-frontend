"""API 请求/响应模型。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SignalRequest(BaseModel):
    type: str = Field("cross", description="cross（双均线交叉）| single（单均线）")
    fast: int = Field(5, ge=1, le=500, description="快线周期")
    slow: int = Field(20, ge=1, le=500, description="慢线周期")
    n: int = Field(20, ge=1, le=500, description="单均线模式的周期")


class MoneyRequest(BaseModel):
    type: str = Field("fixed_count", description="fixed_count（固定股数）| fixed_percent（固定比例）")
    n: int = Field(1000, ge=1, description="每次交易股数")
    percent: float = Field(0.2, gt=0, le=1, description="每次交易占总资金比例")


class OverlayRequest(BaseModel):
    type: str = Field("ma", description="ma | ema | rsi | macd")
    n: int = Field(5, ge=1, le=500)
    key: str | None = None


class StrategyRequest(BaseModel):
    """自定义策略脚本（backend/strategies/<id>.py）。"""

    id: str = Field(..., description="脚本文件名，不含 .py")
    params: dict[str, float] = Field(default_factory=dict, description="脚本声明的参数")


class BacktestRequest(BaseModel):
    symbol: str = Field("sh510300", description="标的代码，如 sh510300")
    start: str = Field("2023-01-01", description="开始日期 YYYY-MM-DD")
    end: str = Field("2024-12-31", description="结束日期 YYYY-MM-DD")
    init_cash: float = Field(300_000.0, gt=0, description="初始资金")
    cost_model: str = Field("etf", description="stock | stock_pre2015 | etf | zero")
    signal: SignalRequest = Field(default_factory=SignalRequest)
    strategy: StrategyRequest | None = Field(
        None, description="设置后忽略 signal，改用自定义脚本"
    )
    money: MoneyRequest = Field(default_factory=MoneyRequest)
    overlays: list[OverlayRequest] = Field(default_factory=list)
    stoploss: float | None = Field(None, gt=0, description="止损百分比，如 0.1 表示 10%")
    takeprofit: float | None = Field(None, gt=0, description="止盈百分比")
    slippage: float | None = Field(None, gt=0, description="滑点百分比")


class JobCreated(BaseModel):
    id: str
    status: str


class SymbolInfo(BaseModel):
    symbol: str
    market: str
    code: str
    name: str
    kind: str
    last_date: str | None = None


class HealthResponse(BaseModel):
    status: str
    engine_ready: bool
    loaded_symbols: int
    available_symbols: int
    cost_models: dict[str, str]
    detail: Any | None = None
