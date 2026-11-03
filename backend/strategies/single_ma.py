"""单均线：收盘价上穿均线买入，下穿卖出。

与双均线一样，周期等参数都在这里声明，界面据 PARAMS 生成表单。
"""
NAME = "单均线"
DESCRIPTION = "收盘价上穿均线买入，下穿均线卖出。"

PARAMS = [
    {"name": "n", "label": "均线周期", "default": 20, "min": 1, "max": 500},
]


def build(params):
    from hikyuu.core import SG_Single
    from hikyuu.indicator import CLOSE, MA

    return SG_Single(MA(CLOSE(), n=params["n"]))
