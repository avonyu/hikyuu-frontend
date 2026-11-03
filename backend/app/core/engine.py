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

import math
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
    SP_FixedPercent,
    ST_FixedPercent,
    SYS_Simple,
    Datetime,
    DatetimeList,
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
class StrategySpec:
    """策略脚本（backend/strategies/<id>.py）。"""

    id: str = ""
    params: dict[str, float | str] = field(default_factory=dict)


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
    strategy: StrategySpec = field(default_factory=StrategySpec)
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


def get_stock(sm, symbol: str):
    """按代码取标的。

    Hikyuu 对未知代码不抛 KeyError，而是返回一个空 Stock（is_null() 为真），
    直接拿去回测会得到晦涩的 HKU_CHECK 异常，所以这里统一检查。
    """
    stock = sm[symbol]
    if stock.is_null():
        raise EngineError(
            f"引擎中没有标的 {symbol}：请先导入数据；"
            "若刚导入或刷新过行情，需要重启后端服务才会加载"
        )
    return stock


def require_kdata(stock, query: Query, symbol: str, start: str, end: str):
    """取区间内的 K 线；区间内没有数据时报错，而不是返回一份空的「成功」结果。"""
    kdata = stock.get_kdata(query)
    if len(kdata) > 0:
        return kdata

    detail = ""
    everything = stock.get_kdata(build_query("1990-01-01", "2099-12-31"))
    if len(everything) > 0:
        first, last = everything[0].datetime, everything[len(everything) - 1].datetime
        detail = (
            f"，本地数据范围 {first.year:04d}-{first.month:02d}-{first.day:02d} ~ "
            f"{last.year:04d}-{last.month:02d}-{last.day:02d}"
        )
    raise EngineError(f"{symbol} 在 {start} ~ {end} 内没有行情数据{detail}")


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
            # Hikyuu 的 MACD 签名是 (data, n1, n2, n3)：短/长 EMA 周期 + 信号线平滑周期
            # 三个结果集依次是：0=BAR(DIFF-DEA)、1=DIFF、2=DEA
            macd = MACD(close, n1=n, n2=26, n3=9)
            bar, diff, dea = (macd.get_result(i) for i in range(3))
            result[f"{key}_macd"] = [float(bar[i]) for i in range(len(bar))]
            result[f"{key}_diff"] = [float(diff[i]) for i in range(len(diff))]
            result[f"{key}_dea"] = [float(dea[i]) for i in range(len(dea))]
            continue
        else:
            raise EngineError(f"未知的指标类型: {kind}")

        result[key] = [float(indicator[i]) for i in range(len(indicator))]

    return result


def _funds_curve(tm, kdata) -> list[dict[str, Any]]:
    """计算资金曲线（账户权益随时间的变化）。

    Hikyuu 的 get_funds_curve 接受一组日期，返回这些日期上的账户权益。
    这里必须用**标的自身的 K 线日期**，不能用市场日历：
    市场日历覆盖整个区间（两年约 484 天），而新上市的标的可能只有
    几十根 K 线（如 sh563360 只有 2024-10 之后的数据）。用市场日历会
    得到一条长度与 K 线对不上、前段全是初始资金的曲线。
    """
    if len(kdata) == 0:
        return []

    dates = DatetimeList([b.datetime for b in kdata])
    values = tm.get_funds_curve(dates, Query.DAY)
    return [
        {
            "time": f"{b.datetime.year:04d}-{b.datetime.month:02d}-{b.datetime.day:02d}",
            "value": float(values[i]) if i < len(values) else float("nan"),
        }
        for i, b in enumerate(kdata)
    ]


def run_backtest(sm, spec: BacktestSpec) -> dict[str, Any]:
    """执行一次回测，返回可直接 JSON 序列化的结果。"""
    stock = get_stock(sm, spec.symbol)
    query = build_query(spec.start, spec.end)
    require_kdata(stock, query, spec.symbol, spec.start, spec.end)

    cost_cls = COST_MODELS.get(spec.cost_model)
    if cost_cls is None:
        raise EngineError(f"未知的成本模型: {spec.cost_model}")

    tm = tmod.crtTM(init_cash=spec.init_cash, cost_func=cost_cls())

    # 自定义策略脚本可以自带资金管理 / 目标价（见 strategies/README.md）
    profit_goal = None
    take_profit = None
    from app.core.strategy_loader import build_parts

    # 上下文让脚本知道当前标的与区间（如定投要按标的取指数估值）
    parts = build_parts(
        spec.strategy.id,
        spec.strategy.params,
        {"symbol": spec.symbol, "start": spec.start, "end": spec.end},
    )
    money = parts.mm if parts.mm is not None else _build_money(spec.money)
    profit_goal = parts.pg
    take_profit = parts.tp

    kwargs: dict[str, Any] = {
        "tm": tm,
        "sg": parts.sg,
        "mm": money,
    }
    if spec.stoploss is not None:
        kwargs["st"] = ST_FixedPercent(spec.stoploss)
    # 止盈走「目标价」槽位（pg）：PG_FixedPercent 的目标价 = 持仓均价 × (1 + p)，
    # 正是定投想要的「盈利到 X% 全部赎回」；tp 槽位是移动止盈，两者不能混用。
    if profit_goal is not None:
        kwargs["pg"] = profit_goal
    elif spec.takeprofit is not None:
        kwargs["pg"] = PG_FixedPercent(spec.takeprofit)
    if take_profit is not None:
        kwargs["tp"] = take_profit
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
    out: dict[str, float] = {}
    # 曲线里偶有 NaN（取不到权益的日子），混进去会让回撤与夏普整体变成 NaN
    equity = [v for v in equity if math.isfinite(v)]
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

    # --- 资金曲线（与 K 线同一批日期，一一对应）---
    equity = _funds_curve(tm, kdata)

    # Hikyuu 未提供回撤与夏普，这里补充
    metrics.update(compute_derived_metrics([e["value"] for e in equity], spec.init_cash))

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
