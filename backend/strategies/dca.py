"""定期定投（估值分位驱动）。

每隔 N 个交易日（或每月首个交易日）看一次标的跟踪指数的估值分位
（PE / PB / ROE，默认近 10 年、至少 3 年样本）：

    pct <= val_low_pct                  低估，买入：amount × low_mult
    val_low_pct < pct < val_high_pct    正常，持有（不买不卖）
    pct >= val_high_pct                 高估，止盈卖出：每期卖出 sell_amount 元
                                        （按 100 股整手，不超过持仓；
                                        持仓不足 1 手则这一期不卖）

`valuation = off` 表示不看估值，每期按固定金额买入（普通定投）。

估值数据是**月度**的，并且会滞后 `val_lag` 个月再使用（月末公布，不能用到当月），
所以它只适合月度或更长的定投节奏；按交易日定投时，一个月的估值对整月生效。

ETF 本身没有 PE/PB/ROE，这里用的是它跟踪指数的估值（见 app/data/valuation.py
的 INDEX_MAP）。科创50、创业板指等没有长历史月度估值的标的，选估值指标运行会
直接报错——它们只能用 `valuation = off` 的普通定投。

注意：

- 本脚本自带资金管理（每期固定金额），表单里的「资金管理」设置对它不生效；
  止损 / 止盈 / 滑点仍由表单控制。
- 买入按 A 股 100 股（1 手）向下取整，金额不足 1 手则该期不买入。
- 每期投入不会超过账户可用现金（预留 1% 手续费空间），现金耗尽后自动停止买入。
"""
from __future__ import annotations

NAME = "定期定投"
DESCRIPTION = (
    "每隔 N 个交易日（或每月首个交易日）定投：按跟踪指数的估值分位（PE/PB/ROE，月度），"
    "低估买入、正常估值持有、高估按设定金额分批止盈卖出。"
)

# 声明本脚本自带资金管理，前端会提示表单里的「资金管理」设置不生效
MONEY_MANAGER = True

PARAMS = [
    {"name": "period", "label": "定投周期(交易日，0=每月)", "default": 0, "min": 0, "max": 250},
    {"name": "amount", "label": "每期投入(元)", "default": 1000, "min": 100, "max": 100000000},
    {
        "name": "valuation",
        "label": "估值指标",
        "type": "choice",
        "choices": ["off", "pe", "pb", "roe"],
        "default": "off",
    },
    {"name": "val_low_pct", "label": "低估分位(%)", "default": 30, "min": 0, "max": 100},
    {"name": "val_high_pct", "label": "高估分位(%)", "default": 70, "min": 0, "max": 100},
    {"name": "val_window", "label": "分位窗口(年)", "default": 10, "min": 1, "max": 20},
    {"name": "val_lag", "label": "估值滞后(月)", "default": 1, "min": 0, "max": 12},
    {"name": "sell_amount", "label": "高估每期卖出(元)", "default": 1000, "min": 0, "max": 100000000},
    {"name": "low_mult", "label": "低估买入倍数", "default": 5.0, "min": 0, "max": 10},
]

LOT = 100  # A 股 / ETF 最小交易单位：1 手 = 100 股


def _buy_bars(kdata, period: int) -> list[int]:
    """定投日对应的 K 线下标。

    period > 0：每 period 个交易日一次（从区间第一根 K 线开始）；
    period == 0：每月第一个交易日（区间第一根 K 线也算一次，保证尽快起投）。
    """
    total = len(kdata)
    if period > 0:
        return list(range(0, total, period))

    bars: list[int] = []
    last_key = None
    for i in range(total):
        dt = kdata[i].datetime
        key = (dt.year, dt.month)
        if key != last_key:
            bars.append(i)
            last_key = key
    return bars


def _valuation_lookup(context: dict, params: dict) -> tuple[str, dict]:
    """按标的取「(年, 月) -> (估值, 分位)」表。

    valuation = off 时返回空表（普通定投）；选了估值指标却拿不到数据则直接报错，
    而不是静默地一笔都不交易。
    """
    metric = str(params["valuation"])
    if metric == "off":
        return metric, {}

    symbol = str((context or {}).get("symbol", "") or "")
    if not symbol:
        raise RuntimeError("缺少标的代码，无法读取估值数据")

    from app.data import valuation

    ref = valuation.get_index_ref(symbol)
    if ref is None:
        raise RuntimeError(
            f"{symbol} 没有登记跟踪指数，无法使用估值指标；请把「估值指标」改为 off"
        )
    if not ref.lg:
        raise RuntimeError(
            f"{ref.name} 没有长历史月度估值（乐咕只提供 {len(valuation.LG_INDICES)} 个指数），"
            f"请把「估值指标」改为 off 使用普通定投"
        )

    table = valuation.percentile_lookup(
        symbol,
        metric=metric,
        window_years=int(params["val_window"]),
        lag_months=int(params["val_lag"]),
    )
    if not table:
        raise RuntimeError(
            f"{ref.name} 的估值数据不可用（首次拉取失败且无缓存），"
            "请检查网络后重试，或把「估值指标」改为 off"
        )
    return metric, table


def _action_for(pct: float, low_pct: float, high_pct: float) -> str:
    """按估值分位决定这一期做什么：buy / hold / sell。

    两个阈值填反了按大小自动纠正；填成一样则只有「买入 / 卖出」两种。
    """
    lo, hi = min(low_pct, high_pct), max(low_pct, high_pct)
    if lo == hi:
        return "sell" if pct >= hi else "buy"
    if pct <= lo:
        return "buy"
    if pct >= hi:
        return "sell"
    return "hold"


def _sell_lots(sell_amount: float, price: float, held: float, lot: int = 100) -> float:
    """按金额算出卖出的股数：100 股整手向下取整，且不超过持仓。"""
    if price <= 0 or sell_amount <= 0 or held <= 0:
        return 0.0
    lots = int(sell_amount / price / lot) * lot
    if lots <= 0:
        return 0.0
    return float(min(lots, held))


def _pct_at(table: dict, dt) -> float | None:
    """取不晚于该月的最近一条分位；没有就返回 None。"""
    key = (dt.year, dt.month)
    if key in table:
        return table[key][1]
    earlier = [k for k in table if k <= key]
    if not earlier:
        return None
    return table[max(earlier)][1]


def build(params, context=None):
    from hikyuu.trade_sys import crtMM, crtSG

    period = int(params["period"])
    amount = float(params["amount"])
    low_mult = float(params["low_mult"])
    sell_amount = float(params["sell_amount"])

    val_table = _valuation_lookup(context or {}, params)[1]
    val_low_pct = float(params["val_low_pct"]) / 100.0
    val_high_pct = float(params["val_high_pct"]) / 100.0

    # SG 与 MM 共享的状态：每个定投日对应的投入倍数
    state: dict[str, list] = {"factors": []}

    def _factor_at(dt) -> float:
        """取不晚于 dt 的最近一次定投倍数。

        资金管理在信号日与成交日各被调用一次（成交日是信号日的下一根 K 线），
        所以这里取「不晚于当前时间」的最大倍数。
        """
        factor = 1.0
        for date, value in state["factors"]:
            if date > dt:
                break
            factor = value
        return factor

    def _calculate(self, kdata):
        """按估值分位决定每一期：低估买入、正常持有、高估分批卖出。"""
        total = len(kdata)
        if total == 0:
            return

        factors: list[tuple] = []
        for i in _buy_bars(kdata, period):
            dt = kdata[i].datetime

            if val_table:
                pct = _pct_at(val_table, dt)
                if pct is not None:
                    action = _action_for(pct, val_low_pct, val_high_pct)
                    if action == "sell":
                        # 卖出信号的值必须为负；具体股数由 _get_sell_num 按金额算
                        self._add_sell_signal(dt, -1.0)
                        factors.append((dt, 0.0))
                        continue
                    if action == "hold":
                        factors.append((dt, 0.0))
                        continue
                    # 低估：按 low_mult 买入（金额在 _get_buy_num 里乘倍数）
                    self._add_buy_signal(dt, max(low_mult, 0.01))
                    factors.append((dt, low_mult))
                    continue
                # 该月没有分位（窗口不足 3 年等）：这一期不动
                factors.append((dt, 0.0))
                continue

            # valuation = off：普通定投，每期按固定金额买入
            factors.append((dt, 1.0))
            self._add_buy_signal(dt, 1.0)

        state["factors"] = factors

    def _get_buy_num(self, datetime, stock, price, risk, part):
        """每期投入固定金额：金额 × 当期倍数，按 100 股整手向下取整。"""
        if price <= 0:
            return 0.0

        budget = amount * _factor_at(datetime)
        # 预留 1% 手续费空间，避免资金差一点导致整笔落空
        tm = self.tm
        cash = tm.cash(datetime) if tm is not None else 0.0
        budget = min(budget, cash * 0.99)
        if budget <= 0:
            return 0.0

        return float(int(budget / price / LOT) * LOT)

    def _get_sell_num(self, datetime, stock, price, risk, part):
        """高估止盈：每期卖出 sell_amount 元，按整手向下取整，且不超过当前持仓。"""
        tm = self.tm
        if tm is None:
            return 0.0
        held = float(tm.get_position(datetime, stock).number)
        return _sell_lots(sell_amount, price, held, LOT)

    sg = crtSG(_calculate, name="SG_DCA")
    # 定投有连续买入与连续卖出：alternate 默认 True 会吞掉同向的后续信号
    sg.set_param("alternate", False)

    mm = crtMM(_get_buy_num, _get_sell_num, name="MM_DCA")
    # 定投是加仓，必须允许在已有持仓时继续买入
    mm.support_mult_buy_sell = True

    return {"sg": sg, "mm": mm}
