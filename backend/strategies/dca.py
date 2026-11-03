"""定期定投（可选智能定投）。

每隔 N 个交易日（或每月首个交易日）投入固定金额买入，买入后继续下一期，
不做择时。适合宽基 ETF 这类长期向上的标的。

「智能定投」：以 N 日均线作估值参考，按收盘价相对均线的偏离线性调整每期金额

    dev    = (close - ma) / ma            # 负数表示低于均线（低估）
    factor = clamp(1 - dev * slope, low_mult, high_mult)

低于均线越多投得越多，高于均线越多投得越少；`ma_n = 0` 时关闭智能定投，
每期金额固定。

注意：

- 本脚本自带资金管理（每期固定金额），表单里的「资金管理」设置对它不生效；
  止损 / 止盈 / 滑点仍由表单控制。
- 买入按 A 股 100 股（1 手）向下取整，金额不足 1 手则该期不买入。
- 每期投入不会超过账户可用现金（预留 1% 手续费空间），现金耗尽后自动停止买入。
"""
from __future__ import annotations

NAME = "定期定投"
DESCRIPTION = (
    "每隔 N 个交易日（或每月首个交易日）投入固定金额买入；"
    "可按价格相对均线的偏离智能调整每期金额（低估多投、高估少投）。"
)

# 声明本脚本自带资金管理，前端会提示表单里的「资金管理」设置不生效
MONEY_MANAGER = True

PARAMS = [
    {"name": "period", "label": "定投周期(交易日，0=每月)", "default": 0, "min": 0, "max": 250},
    {"name": "amount", "label": "每期投入(元)", "default": 1000, "min": 100, "max": 100000000},
    {"name": "ma_n", "label": "参考均线周期(0=不启用)", "default": 60, "min": 0, "max": 500},
    {"name": "slope", "label": "偏离灵敏度", "default": 2.0, "min": 0, "max": 20},
    {"name": "low_mult", "label": "低估投入倍数", "default": 5.0, "min": 0, "max": 10},
    {"name": "high_mult", "label": "高估投入倍数", "default": 0.0, "min": 0, "max": 10},
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


def build(params):
    from hikyuu.indicator import CLOSE, MA
    from hikyuu.trade_sys import crtMM, crtSG

    period = int(params["period"])
    amount = float(params["amount"])
    ma_n = int(params["ma_n"])
    slope = float(params["slope"])
    low_mult = float(params["low_mult"])
    high_mult = float(params["high_mult"])

    # 倍数区间，用户填反了也不至于算出反向的结果
    low = min(low_mult, high_mult)
    high = max(low_mult, high_mult)

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
        """产生定期买入信号，并算出每期的投入倍数。"""
        total = len(kdata)
        if total == 0:
            return

        ma = MA(CLOSE(kdata), n=ma_n) if ma_n > 0 else None

        factors: list[tuple] = []
        for i in _buy_bars(kdata, period):
            factor = 1.0
            if ma is not None and i >= ma.discard:
                ref = ma[i]
                if ref == ref and ref > 0:  # 排除 NaN 与无效值
                    dev = (kdata[i].close - ref) / ref
                    factor = min(max(1.0 - dev * slope, low), high)
            factors.append((kdata[i].datetime, factor))
            # 信号值必须为正：净值为 0 的 bar 会被引擎当成「无信号」丢弃
            self._add_buy_signal(kdata[i].datetime, max(factor, 0.01))

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

    sg = crtSG(_calculate, name="SG_DCA")
    # 定投每期都是买入：alternate 默认 True 会吞掉连续的买入信号
    sg.set_param("alternate", False)

    mm = crtMM(_get_buy_num, name="MM_DCA")
    # 定投是加仓，必须允许在已有持仓时继续买入
    mm.support_mult_buy_sell = True

    return {"sg": sg, "mm": mm}
