"""双均线交叉：快线上穿慢线买入，下穿卖出。

这是自定义策略的最小示例，可直接复制改名作为模板。
"""
NAME = "双均线交叉"
DESCRIPTION = "快线上穿慢线买入，下穿卖出。"

PARAMS = [
    {"name": "fast", "label": "快线周期", "default": 5, "min": 1, "max": 500},
    {"name": "slow", "label": "慢线周期", "default": 20, "min": 2, "max": 500},
]


def build(params):
    from hikyuu.core import SG_Cross
    from hikyuu.indicator import CLOSE, MA

    close = CLOSE()
    return SG_Cross(
        MA(close, n=params["fast"]),
        MA(close, n=params["slow"]),
    )
