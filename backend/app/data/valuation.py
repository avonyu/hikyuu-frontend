"""指数估值数据（PE / PB / ROE）与历史分位。

ETF 本身没有 PE/PB/ROE——它只是基金份额，估值属于它跟踪的指数。
这里用乐咕乐股（legulegu）的指数估值：月度、2005 年起，覆盖 12 个主流宽基。
中证指数官网也有估值，但只给最近 20 个交易日且没有 PB，无法做长历史回测，
所以只在没有乐咕数据时作为补充说明，不参与分位计算。

ROE 用同一时点的 PB ÷ PE（整体法，静态 PE）推算：

    ROE = (P / B) ÷ (P / E) = E / B

数据落盘为 CSV，首次联网、之后离线；刷新只补新月份。
所有对外接口都会**滞后**若干月再返回，避免把月末才公布的数据用到当月决策上。
"""
from __future__ import annotations

import math
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from app.config import CFG_DIR

VALUATION_DIR = CFG_DIR / "valuation"

# 缓存超过这个天数就重新拉取（乐咕按日更新，但估值是月频，7 天足够）
CACHE_MAX_AGE_DAYS = 7

# 分位计算的最少样本数（月）：3 年，少于这个数不给分位，避免早期噪声
MIN_PERCENTILE_MONTHS = 36


@dataclass(frozen=True)
class IndexRef:
    """ETF 跟踪的指数。lg 为乐咕乐股使用的指数中文简称，没有则拿不到长历史估值。"""

    code: str
    name: str
    lg: str | None = None


# ETF -> 跟踪指数。默认标的里的科创50、创业板指不在乐咕的 12 个指数里，
# lg 留空：此时「估值」指标不可用，策略会回退到均线偏离。
INDEX_MAP: dict[str, IndexRef] = {
    # 沪深300
    "sh510300": IndexRef("000300", "沪深300", "沪深300"),
    "sz159919": IndexRef("000300", "沪深300", "沪深300"),
    # 上证50 / 中证500
    "sh510050": IndexRef("000016", "上证50", "上证50"),
    "sh510500": IndexRef("000905", "中证500", "中证500"),
    # 中证1000 / 中证800 / 中证100
    "sh512100": IndexRef("000852", "中证1000", "中证1000"),
    "sh515800": IndexRef("000906", "中证800", "中证800"),
    "sh512910": IndexRef("000903", "中证100", "中证100"),
    # 深证100 / 深证红利 / 上证180 / 上证380 / 上证红利 / 创业板50
    "sz159901": IndexRef("399330", "深证100", "深证100"),
    "sz159905": IndexRef("399324", "深证红利", "深证红利"),
    "sh510180": IndexRef("000010", "上证180", "上证180"),
    "sh510330": IndexRef("000300", "沪深300", "沪深300"),
    "sh510880": IndexRef("000015", "上证红利", "上证红利"),
    "sz159949": IndexRef("399673", "创业板50", "创业板50"),
    # 没有长历史月度估值的（乐咕不提供）：仍保留映射，用于前端提示与后续扩展
    "sh588000": IndexRef("000688", "科创50"),
    "sz159915": IndexRef("399006", "创业板指"),
}

# 乐咕提供估值的 12 个指数，用于给用户提示「这个标的有/没有估值」
LG_INDICES = (
    "上证50", "沪深300", "上证380", "创业板50", "中证500", "上证180",
    "深证红利", "深证100", "中证1000", "上证红利", "中证100", "中证800",
)

METRICS = ("pe", "pe_ttm", "pb", "roe")


class ValuationError(RuntimeError):
    """估值数据不可用（没有映射 / 拉取失败且无缓存）。"""


def get_index_ref(symbol: str) -> IndexRef | None:
    return INDEX_MAP.get((symbol or "").lower())


def supports_valuation(symbol: str) -> bool:
    ref = get_index_ref(symbol)
    return bool(ref and ref.lg)


def _cache_file(ref: IndexRef) -> Path:
    return VALUATION_DIR / f"{ref.lg}.csv"


def _read_cache(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, parse_dates=["date"])
    except (OSError, ValueError, pd.errors.ParserError):
        return None
    if df.empty or not {"date", "pe", "pb"}.issubset(df.columns):
        return None
    return df.sort_values("date").reset_index(drop=True)


def _write_cache(path: Path, df: pd.DataFrame) -> None:
    """原子写入，写到一半失败不会留下半截 CSV。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        df.to_csv(tmp, index=False)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _fetch_from_legulegu(lg_name: str) -> pd.DataFrame:
    """从乐咕乐股拉 PE / PB 并合成 ROE。两张表都按月，按日期内连接。"""
    import akshare as ak

    try:
        pe_df = ak.stock_index_pe_lg(symbol=lg_name)
        pb_df = ak.stock_index_pb_lg(symbol=lg_name)
    except Exception as exc:  # noqa: BLE001 - 网络与上游格式都可能出错
        raise ValuationError(f"拉取 {lg_name} 估值失败：{type(exc).__name__}: {exc}") from exc

    if pe_df is None or pb_df is None or pe_df.empty or pb_df.empty:
        raise ValuationError(f"{lg_name} 的估值数据为空")

    pe = pe_df.rename(
        columns={"日期": "date", "静态市盈率": "pe", "滚动市盈率": "pe_ttm"}
    )[["date", "pe", "pe_ttm"]]
    pb = pb_df.rename(columns={"日期": "date", "市净率": "pb"})[["date", "pb"]]

    pe["date"] = pd.to_datetime(pe["date"])
    pb["date"] = pd.to_datetime(pb["date"])

    df = pe.merge(pb, on="date", how="inner").sort_values("date").reset_index(drop=True)
    for col in ("pe", "pe_ttm", "pb"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = add_roe(df)
    df = df.dropna(subset=["date", "pe", "pb"])
    if df.empty:
        raise ValuationError(f"{lg_name} 的估值日期无法对齐")
    return df


def add_roe(df: pd.DataFrame) -> pd.DataFrame:
    """ROE = PB ÷ PE（整体法、静态 PE）。PE ≤ 0（整体亏损）时 ROE 无意义，置空。"""
    out = df.copy()
    out["roe"] = [
        (pb_v / pe_v * 100.0) if pe_v and pe_v > 0 and math.isfinite(pb_v) else float("nan")
        for pe_v, pb_v in zip(out["pe"], out["pb"])
    ]
    return out


def load_valuation(symbol: str, force: bool = False) -> pd.DataFrame:
    """取某个 ETF 对应指数的月度估值：date / pe / pe_ttm / pb / roe。

    有缓存且未过期就直接用；拉取失败时退回旧缓存（离线可用）。
    """
    ref = get_index_ref(symbol)
    if ref is None:
        raise ValuationError(f"没有 {symbol} 的指数映射")
    if not ref.lg:
        raise ValuationError(f"{ref.name} 没有可用的月度估值数据")

    path = _cache_file(ref)
    cached = _read_cache(path)
    fresh_enough = (
        cached is not None
        and not force
        and (time.time() - path.stat().st_mtime) < CACHE_MAX_AGE_DAYS * 86400
    )
    if fresh_enough:
        return cached

    try:
        df = _fetch_from_legulegu(ref.lg)
    except ValuationError:
        if cached is not None:
            return cached
        raise
    _write_cache(path, df)
    return df


def percentile_series(
    df: pd.DataFrame,
    metric: str = "pe",
    window_years: int = 10,
    lag_months: int = 1,
) -> pd.DataFrame:
    """在月度估值上算历史分位，并把结果滞后 lag_months 个月。

    分位只使用「当前月及以前」的样本，再整体后移，所以策略拿到的每一天，
    用到的都是当时已经公布的数据（避免未来函数）。

    返回列：date（滞后后的生效月份）、value、pct（0~1）。
    """
    if metric not in METRICS:
        raise ValuationError(f"未知估值指标：{metric}")

    series = df[["date", metric]].dropna().sort_values("date").reset_index(drop=True)
    if series.empty:
        raise ValuationError(f"估值数据里没有 {metric}")

    values = series[metric].to_numpy(dtype=float)
    window = max(12, int(window_years) * 12)
    pcts: list[float] = []
    for i, value in enumerate(values):
        start = max(0, i - window + 1)
        chunk = values[start : i + 1]
        if len(chunk) < MIN_PERCENTILE_MONTHS:
            pcts.append(float("nan"))
            continue
        pcts.append(float((chunk <= value).mean()))

    series["pct"] = pcts
    if lag_months > 0:
        series["value"] = series[metric].shift(lag_months)
        series["pct"] = series["pct"].shift(lag_months)
    else:
        series["value"] = series[metric]

    return series[["date", "value", "pct"]].dropna().reset_index(drop=True)


def percentile_lookup(
    symbol: str,
    metric: str = "pe",
    window_years: int = 10,
    lag_months: int = 1,
) -> dict[tuple[int, int], tuple[float, float]]:
    """(年, 月) -> (估值, 分位)。策略按 K 线所在月份查表，找不到就用更早的月份。

    没有映射或拉取失败时返回空字典，调用方回退到别的逻辑。
    """
    try:
        df = load_valuation(symbol)
        series = percentile_series(df, metric, window_years, lag_months)
    except (ValuationError, OSError, ValueError):
        # 没有数据 / 断网 / 缓存损坏都回退到别的逻辑，不让一次回测失败
        return {}

    out: dict[tuple[int, int], tuple[float, float]] = {}
    for date, value, pct in zip(series["date"], series["value"], series["pct"]):
        out[(int(date.year), int(date.month))] = (float(value), float(pct))
    return out
