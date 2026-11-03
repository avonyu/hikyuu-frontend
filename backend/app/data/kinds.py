"""证券代码 → 市场 / 类别识别。

A 股的代码空间按「市场 + 代码段」划分，同一个 6 位数字在不同市场是不同
标的（`sh000001` 是上证指数，`sz000001` 是平安银行），所以判定必须同时
看市场和代码。

这里只做离线的前缀规则：快、不依赖网络，也避免为了判定一个标的去拉
30 秒的全市场清单。规则依据 2026-11 各数据源清单的实测分布：

    ETF   1664 条：15/51/56/58 为主，另有 52/53
    INDEX  732 条：39（深市）、00（沪市/中证）
    STOCK 5578 条：60/68（沪）、00/30（深）、92（北交所）

已知边界：
- 深市 16xxxx 多为 LOF，这里归 ETF（行情接口与 ETF 相同）；
- 沪市 000xxx 是指数、深市 000xxx 是股票，所以 `000` 段裸代码无法判定
  市场，必须写前缀。
"""
from __future__ import annotations

KIND_ETF = "ETF"
KIND_STOCK = "STOCK"
KIND_INDEX = "INDEX"

KINDS = (KIND_ETF, KIND_STOCK, KIND_INDEX)

# (market, code prefixes, kind)
_RULES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("SH", ("000", "999"), KIND_INDEX),
    ("SH", ("5",), KIND_ETF),  # 沪市 5xxxxx 全是场内基金（ETF/LOF）
    ("SH", ("60", "68"), KIND_STOCK),
    ("SZ", ("399",), KIND_INDEX),
    ("SZ", ("15", "16"), KIND_ETF),
    ("SZ", ("00", "30"), KIND_STOCK),
    ("BJ", ("43", "83", "87", "92"), KIND_STOCK),
)

# 无市场前缀时用来推断市场；000 段有歧义，故意不给
_MARKET_BY_PREFIX: tuple[tuple[str, str], ...] = (
    ("399", "SZ"),
    ("15", "SZ"),
    ("16", "SZ"),
    ("30", "SZ"),
    ("001", "SZ"),
    ("002", "SZ"),
    ("003", "SZ"),
    ("43", "BJ"),
    ("83", "BJ"),
    ("87", "BJ"),
    ("92", "BJ"),
    ("60", "SH"),
    ("68", "SH"),
    ("51", "SH"),
    ("52", "SH"),
    ("53", "SH"),
    ("56", "SH"),
    ("58", "SH"),
    ("5", "SH"),  # 其余 5xxxxx 场内基金
    ("999", "SH"),
)


class KindError(ValueError):
    """代码格式不合法，或类别/市场无法判定。"""


def normalize_code(raw: str) -> str:
    """校验并返回 6 位数字代码。"""
    code = raw.strip()
    if not (len(code) == 6 and code.isdigit()):
        raise KindError(f"代码必须是 6 位数字：{raw!r}")
    return code


def infer_market(code: str) -> str | None:
    """按代码段推断市场；`000` 段（沪指 vs 深股）返回 None 表示有歧义。"""
    for prefix, market in _MARKET_BY_PREFIX:
        if code.startswith(prefix):
            return market
    return None


def resolve_kind(market: str, code: str, explicit: str | None = None) -> tuple[str, str]:
    """返回 (kind, 判定依据)。explicit 非空时优先使用。"""
    market = market.upper()
    if explicit:
        kind = explicit.strip().upper()
        if kind not in KINDS:
            raise KindError(f"未知类别 {explicit!r}，可选 {', '.join(KINDS)}")
        return kind, "--kind 指定"

    for rule_market, prefixes, kind in _RULES:
        if rule_market != market:
            continue
        for prefix in prefixes:
            if code.startswith(prefix):
                return kind, f"{market} {prefix} 段"
    raise KindError(f"无法判定 {market}{code} 的类别，请用 --kind 显式指定")
