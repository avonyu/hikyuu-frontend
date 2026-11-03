"""RSI 超买超卖：低位买入、高位卖出。

演示如何用 SG_Bool + 指标比较表达式写策略。
"""
NAME = "RSI 超买超卖"
DESCRIPTION = "RSI 低于买入阈值时买入，高于卖出阈值时卖出。"

PARAMS = [
    {"name": "n", "label": "RSI 周期", "default": 14, "min": 2, "max": 200},
    {"name": "buy", "label": "买入阈值", "default": 30, "min": 1, "max": 99},
    {"name": "sell", "label": "卖出阈值", "default": 70, "min": 1, "max": 99},
]


def build(params):
    from hikyuu.core import SG_Bool
    from hikyuu.indicator import CLOSE, RSI

    rsi = RSI(CLOSE(), n=params["n"])
    return SG_Bool(rsi < params["buy"], rsi > params["sell"])
