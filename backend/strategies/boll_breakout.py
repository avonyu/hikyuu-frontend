"""布林带突破：收盘突破上轨买入，跌破中轨卖出。

演示指标算术运算（中轨 + k × 标准差）。
"""
NAME = "布林带突破"
DESCRIPTION = "收盘价突破上轨买入，跌破中轨卖出。"

PARAMS = [
    {"name": "n", "label": "周期", "default": 20, "min": 2, "max": 200},
    {"name": "k", "label": "带宽倍数", "default": 2, "min": 0.5, "max": 5},
]


def build(params):
    from hikyuu.core import SG_Bool
    from hikyuu.indicator import CLOSE, MA, STD

    close = CLOSE()
    mid = MA(close, n=params["n"])
    upper = mid + STD(close, n=params["n"]) * params["k"]
    return SG_Bool(close > upper, close < mid)
