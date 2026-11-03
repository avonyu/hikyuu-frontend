"""Hikyuu 3.0 引擎适配层。

把 Hikyuu 的版本差异全部封在这一层，上层不直接依赖 hikyuu。

已处理并实测验证的 3.0 差异：
1. 策略组件从 `hikyuu.trade_sys` 移到 `hikyuu.core`
2. `Query(int, int)` 现在表示「bar 索引」而非日期，传日期会静默返回 0 条，
   日期区间必须用 `Query(Datetime(y,m,d), Datetime(y,m,d))`
3. `Query` 的结束日期是排他的——`Query(…, 2024-12-31)` 最后一根是 12-30，
   需要 +1 天才会把用户填的当天纳入
4. 指标必须绑定到具体的 KData（`CLOSE(kdata)`），否则长度为 0
5. `TradeRecord.is_null` 是方法而非属性，当属性判断会跳过全部成交
6. 成交列表首项是 business=INIT 的账户初始化占位记录，不是真实成交
7. 证券代码在库中是大写（SH510300），查询用小写（sh510300）
8. `get_funds_curve` 需要交易日历，而日历由市场主指数推导
9. Performance 报表不含最大回撤与夏普比率，需从资金曲线自行计算
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any

warnings.filterwarnings("ignore")

import hikyuu as hku
from hikyuu.core import (
    MM_FixedCount,
    MM_FixedPercent,
    PG_FixedPercent,
    Query,
    SG_Cross,
    SG_Single,
    SP_FixedPercent,
    ST_FixedPercent,
    SYS_Simple,
    Datetime,
)
import hikyuu.trade_manage as tmod

# A 股成本模型（Hikyuu 内置）
#   TC_FixedA2017: 佣金 0.0018 / 最低 5 元 / 印花税 0.001 / 过户费 0.00002
#   TC_FixedETF:   佣金 0.0001 / 最低 5 元，无印花税
#   TC_FixedAPre2015: 2015 年前费率
COST_MODELS = {
    "stock": tmod.TC_FixedA2017,
    "stock_pre2015": tmod.TC_FixedAPre2015,
    "etf": tmod.TC_FixedETF,
    "zero": tmod.TC_Zero,
}

COST_MODEL_LABELS = {
    "stock": "股票费率（2017 起，印花税 0.1%）",
    "stock_pre2015": "股票费率（2015 前，印花税 0.3%）",
    "etf": "ETF 费率（佣金 0.01%，无印花税）",
    "zero": "零费用",
}


@dataclass
class SignalSpec:
    """信号发生器配置。"""

    type: str = "cross"          # cross | single
    fast: int = 5
    slow: int = 20
    n: int = 20                 # single 类型使用


@dataclass
class StrategySpec:
    """自定义策略脚本（backend/strategies/<id>.py）。"""

    id: str = ""
    params: dict[str, float] = field(default_factory=dict)


@dataclass
class MoneySpec:
    """资金管理配置。"""

    type: str = "fixed_count"    # fixed_count | fixed_percent
    n: int = 1000               # 固定股数
    percent: float = 0.2        # 固定比例


@dataclass
class OverlaySpec:
    """K 线图上的指标叠加线。"""

    type: str = "ma"            # ma | ema | rsi | macd
    n: int = 5
    key: str | None = None


@dataclass
class BacktestSpec:
    """一次回测的完整描述。"""

    symbol: str = "sh510300"
    start: str = "2023-01-01"
    end: str = "2024-12-31"
    init_cash: float = 300_000.0
    cost_model: str = "etf"
    signal: SignalSpec = field(default_factory=SignalSpec)
    strategy: StrategySpec | None = None    # 非空时优先于 signal
    money: MoneySpec = field(default_factory=MoneySpec)
    overlays: list[OverlaySpec] = field(default_factory=list)
    stoploss: float | None = None      # 止损百分比
    takeprofit: float | None = None    # 止盈百分比
    slippage: float | None = None      # 滑点百分比


class EngineError(RuntimeError):
    """回测执行失败。"""


def load_hikyuu(config_file: str, symbols: list[str]):
    """加载 Hikyuu 数据，返回 StockManager。"""
    hku.load_hikyuu(
        config_file=config_file,
        stock_list=symbols,
        ktype_list=["day"],
        load_history_finance=False,
        load_weight=False,
        start_spot=False,
        lazy_preload=False,
    )
    return hku.StockManager.instance()


def build_query(start: str, end: str) -> Query:
    """构造日期区间查询。

    Hikyuu 3.0 中 Query(int, int) 表示 bar 索引，日期区间必须用 Datetime，
    否则会静默返回空结果。

    注意：结束日期是**排他**的——Query(…, 2024-12-31) 的最后一根是 12-30。
    为了让用户填的结束日期当天真正被纳入，这里加一天。
    """
    import datetime as dt

    s = Datetime(*[int(x) for x in start.split("-")])
    end_date = dt.date.fromisoformat(end) + dt.timedelta(days=1)
    e = Datetime(end_date.year, end_date.month, end_date.day)
    return Query(s, e)


def _build_signal(spec: SignalSpec):
    from hikyuu.indicator import CLOSE, EMA, MA

    if spec.type == "cross":
        fast = MA(CLOSE(), n=spec.fast)
        slow = MA(CLOSE(), n=spec.slow)
        return SG_Cross(fast, slow)
    if spec.type == "single":
        return SG_Single(MA(CLOSE(), n=spec.n))
    raise EngineError(f"未知的信号类型: {spec.type}")


def _build_money(spec: MoneySpec):
    if spec.type == "fixed_count":
        return MM_FixedCount(spec.n)
    if spec.type == "fixed_percent":
        return MM_FixedPercent(spec.percent)
    raise EngineError(f"未知的资金管理类型: {spec.type}")


def extract_overlays(kdata, overlays: list[OverlaySpec]) -> dict[str, list[float]]:
    """计算指标叠加线，长度与 KData 一致。

    注意：指标必须从已绑定的 CLOSE(kdata) 构造，否则长度为 0。
    """
    from hikyuu.indicator import CLOSE, EMA, MA, MACD, RSI

    close = CLOSE(kdata)
    result: dict[str, list[float]] = {}

    for overlay in overlays:
        kind = overlay.type
        n = int(overlay.n)
        key = overlay.key or f"{kind}{n}"

        if kind == "ma":
            indicator = MA(close, n=n)
        elif kind == "ema":
            indicator = EMA(close, n=n)
        elif kind == "rsi":
            indicator = RSI(close, n=n)
        elif kind == "macd":
            macd = MACD(close, n=n, m1=12, m2=26)
            result[f"{key}_macd"] = [float(macd.macd[i]) for i in range(len(macd.macd))]
            result[f"{key}_diff"] = [float(macd.diff[i]) for i in range(len(macd.diff))]
            result[f"{key}_dea"] = [float(macd.dea[i]) for i in range(len(macd.dea))]
            continue
        else:
            raise EngineError(f"未知的指标类型: {kind}")

        result[key] = [float(indicator[i]) for i in range(len(indicator))]

    return result


def _calendar_for(sm, query: Query):
    """取交易日历。

    Hikyuu 的日历来自市场主指数（沪深取 sh000300），拿不到日历时
    get_funds_curve 会返回空数组。
    """
    codes = [s.market_code.lower() for s in sm]
    for code in ("sh000300", "sh000001"):
        if code in codes:
            try:
                return sm[code].get_trading_calendar(query)
            except Exception:  # noqa: BLE001
                continue
    return None


def run_backtest(sm, spec: BacktestSpec) -> dict[str, Any]:
    """执行一次回测，返回可直接 JSON 序列化的结果。"""
    try:
        stock = sm[spec.symbol]
    except KeyError as exc:
        raise EngineError(f"未找到标的 {spec.symbol}，请先导入数据") from exc

    query = build_query(spec.start, spec.end)

    cost_cls = COST_MODELS.get(spec.cost_model)
    if cost_cls is None:
        raise EngineError(f"未知的成本模型: {spec.cost_model}")

    tm = tmod.crtTM(init_cash=spec.init_cash, cost_func=cost_cls())

    if spec.strategy is not None:
        from app.core.strategy_loader import build_signal

        signal = build_signal(spec.strategy.id, spec.strategy.params)
    else:
        signal = _build_signal(spec.signal)

    kwargs: dict[str, Any] = {
        "tm": tm,
        "sg": signal,
        "mm": _build_money(spec.money),
    }
    if spec.stoploss is not None:
        kwargs["st"] = ST_FixedPercent(spec.stoploss)
    if spec.takeprofit is not None:
        kwargs["tp"] = PG_FixedPercent(spec.takeprofit)
    if spec.slippage is not None:
        kwargs["sp"] = SP_FixedPercent(spec.slippage)

    system = SYS_Simple(**kwargs)
    system.run(stock, query)

    return _collect_results(sm, tm, stock, query, spec)


def compute_derived_metrics(equity: list[float], init_cash: float) -> dict[str, float]:
    """从资金曲线补充 Hikyuu 未提供的指标。

    Hikyuu 的 Performance 报表不含最大回撤与夏普比率，这里按标准定义计算：
    - 最大回撤：资金曲线相对历史最高点的最大跌幅
    - 夏普比率：日收益均值 / 标准差 × √252（无风险利率按 0）
    """
    import math

    out: dict[str, float] = {}
    if not equity:
        return out

    # --- 最大回撤 ---
    peak = equity[0]
    max_drawdown = 0.0
    for value in equity:
        if value > peak:
            peak = value
        if peak > 0:
            drawdown = (peak - value) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown
    out["Max Drawdown %"] = max_drawdown * 100

    # --- 收益相关 ---
    if init_cash > 0:
        out["Account Total Return %"] = (equity[-1] - init_cash) / init_cash * 100

    # --- 夏普比率 ---
    returns = []
    for i in range(1, len(equity)):
        prev = equity[i - 1]
        if prev > 0:
            returns.append((equity[i] - prev) / prev)
    if len(returns) >= 2:
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        std = math.sqrt(variance)
        out["Sharpe Ratio"] = (mean / std) * math.sqrt(252) if std > 0 else 0.0
        # 年化波动率
        out["Annualized Volatility %"] = std * math.sqrt(252) * 100

    return out


def _collect_results(sm, tm, stock, query: Query, spec: BacktestSpec) -> dict[str, Any]:
    """把回测结果整理成 JSON 友好的结构。"""

    # --- 绩效指标（Hikyuu 内置 53 项 + 本层补充的回撤/夏普等）---
    perf_df = tm.get_performance().to_df()
    metrics = {str(row["name"]): float(row["value"]) for _, row in perf_df.iterrows()}

    # --- K 线 ---
    kdata = stock.get_kdata(query)
    candles = [
        {
            "time": f"{b.datetime.year:04d}-{b.datetime.month:02d}-{b.datetime.day:02d}",
            "open": float(b.open),
            "high": float(b.high),
            "low": float(b.low),
            "close": float(b.close),
            "volume": float(b.volume),
        }
        for b in kdata
    ]

    # --- 资金曲线 ---
    calendar = _calendar_for(sm, query)
    equity: list[float] = []
    if calendar is not None and len(calendar) > 0:
        equity = [float(v) for v in tm.get_funds_curve(calendar, Query.DAY)]

    # Hikyuu 未提供回撤与夏普，这里补充
    metrics.update(compute_derived_metrics(equity, spec.init_cash))

    # --- 成交记录 ---
    trades = []
    for record in tm.get_trade_list():
        # is_null 是方法不是属性；当成属性判断会跳过全部成交
        if record.is_null():
            continue
        business = str(record.business).split(".")[-1]
        # INIT 是账户初始化的占位记录，不是真实成交
        if business == "INIT":
            continue
        trades.append(
            {
                "datetime": str(record.datetime),
                "code": record.stock.market_code.lower() if record.stock is not None else "",
                "name": record.stock.name if record.stock is not None else "",
                "business": business,
                "price": float(record.real_price),
                "plan_price": float(record.plan_price),
                "number": float(record.number),
                "cash": float(record.cash),
                "cost": {
                    "commission": float(record.cost.commission),
                    "stamp_tax": float(record.cost.stamptax),
                    "transfer_fee": float(record.cost.transferfee),
                    "others": float(record.cost.others),
                },
            }
        )

    # --- 指标叠加线 ---
    overlays = extract_overlays(kdata, spec.overlays) if spec.overlays else {}

    return {
        "symbol": spec.symbol,
        "start": spec.start,
        "end": spec.end,
        "init_cash": spec.init_cash,
        "cost_model": spec.cost_model,
        "metrics": metrics,
        "candles": candles,
        "equity": equity,
        "trades": trades,
        "overlays": overlays,
    }
