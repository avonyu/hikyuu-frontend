"""行情数据源适配。

akshare 是主力数据源；指数走腾讯接口——实测 akshare 原生指数接口需 26s，
腾讯源仅 0.22s，差 100 倍。
"""
from __future__ import annotations

import pandas as pd

# 统一列：open/high/low/close/volume/amount
COLUMNS = ["open", "high", "low", "close", "volume", "amount"]

# akshare 字段名 -> 统一列名
AK_RENAME = {
    "日期": "date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
}

# 证券类型（与 Hikyuu 的 STOCKTYPE 对齐）
KIND_ETF = "ETF"
KIND_INDEX = "INDEX"
KIND_STOCK = "STOCK"


class DataSourceError(RuntimeError):
    """数据拉取失败。"""


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """统一列名、类型与索引，并按日期升序。"""
    if df is None or df.empty:
        raise DataSourceError("数据源返回空数据")

    df = df.rename(columns=AK_RENAME)
    if "date" not in df.columns:
        raise DataSourceError(f"数据源缺少日期列，实际列: {list(df.columns)}")

    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df = df[~df.index.duplicated(keep="last")]

    for col in COLUMNS:
        if col not in df.columns:
            df[col] = 0.0

    df = df[COLUMNS].astype(float)
    df["volume"] = df["volume"].fillna(0.0)
    df["amount"] = df["amount"].fillna(0.0)
    # 价格缺失的行（停牌、数据源脏数据）无法入库，写 HDF5 时会直接报错，这里先丢掉
    df = df.dropna(subset=["open", "high", "low", "close"])
    if df.empty:
        raise DataSourceError("数据源返回的行情全部缺少价格")
    return df


def today_str() -> str:
    """今天，YYYYMMDD。结束日期默认取它，否则拉不到写死日期之后的新行情。"""
    import datetime as dt

    return dt.date.today().strftime("%Y%m%d")


def fetch_etf(code: str, start: str = "20180101", end: str | None = None) -> pd.DataFrame:
    """场内 ETF 日线（前复权）。"""
    import akshare as ak

    end = end or today_str()

    try:
        df = ak.fund_etf_hist_em(
            symbol=code, period="daily", start_date=start, end_date=end, adjust="qfq"
        )
    except Exception as exc:  # noqa: BLE001
        raise DataSourceError(f"拉取 ETF {code} 失败: {exc}") from exc
    return _normalize(df)


def fetch_stock(code: str, start: str = "20180101", end: str | None = None) -> pd.DataFrame:
    """A 股日线（前复权）。"""
    import akshare as ak

    end = end or today_str()

    try:
        df = ak.stock_zh_a_hist(
            symbol=code, period="daily", start_date=start, end_date=end, adjust="qfq"
        )
    except Exception as exc:  # noqa: BLE001
        raise DataSourceError(f"拉取股票 {code} 失败: {exc}") from exc
    return _normalize(df)


def fetch_index(market: str, code: str, start: str = "20180101", end: str | None = None) -> pd.DataFrame:
    """指数日线。走腾讯源，比 akshare 原生指数接口快约 100 倍。

    腾讯接口要求 symbol 带市场前缀（sh000001 / sz399006），且一次返回
    全历史，start/end 不生效。
    """
    import akshare as ak

    symbol = f"{market.lower()}{code}"
    try:
        df = ak.stock_zh_index_daily_tx(symbol=symbol)
    except Exception as exc:  # noqa: BLE001
        raise DataSourceError(f"拉取指数 {symbol} 失败: {exc}") from exc

    df = df.rename(columns={"date": "date", "open": "open", "close": "close",
                            "high": "high", "low": "low"})
    df["volume"] = 0.0
    df["amount"] = 0.0
    return _normalize(df)


def fetch_any(market: str, code: str, kind: str,
              start: str = "20180101", end: str | None = None) -> pd.DataFrame:
    """按证券类型选择数据源。"""
    if kind == KIND_ETF:
        return fetch_etf(code, start, end)
    if kind == KIND_INDEX:
        return fetch_index(market, code, start, end)
    if kind == KIND_STOCK:
        return fetch_stock(code, start, end)
    raise DataSourceError(f"未知证券类型: {kind}")


def fetch_incremental(market: str, code: str, kind: str, last_date: str | None,
                      start: str = "20180101", end: str | None = None) -> pd.DataFrame:
    """增量拉取：已有数据的标的只取 last_date 之后的部分。"""
    if last_date:
        # 多取 10 天用于覆盖停牌与除权导致的缺口
        start = _shift_days(last_date, -10)
    return fetch_any(market, code, kind, start, end)


def _shift_days(date_str: str, days: int) -> str:
    import datetime as dt

    d = dt.date.fromisoformat(date_str[:10]) + dt.timedelta(days=days)
    return d.strftime("%Y%m%d")


def list_etf() -> pd.DataFrame:
    """场内 ETF 清单（代码、名称）。"""
    import akshare as ak

    try:
        df = ak.fund_etf_spot_em()
    except Exception as exc:  # noqa: BLE001
        raise DataSourceError(f"拉取 ETF 清单失败: {exc}") from exc
    return df[["代码", "名称"]].rename(columns={"代码": "code", "名称": "name"})


def list_index() -> pd.DataFrame:
    """指数清单（代码、名称）。"""
    import akshare as ak

    try:
        df = ak.index_stock_info()
    except Exception as exc:  # noqa: BLE001
        raise DataSourceError(f"拉取指数清单失败: {exc}") from exc
    return df.rename(columns={"index_code": "code", "display_name": "name"})


def list_stock() -> pd.DataFrame:
    """A 股清单（代码、名称）。"""
    import akshare as ak

    try:
        df = ak.stock_info_a_code_name()
    except Exception as exc:  # noqa: BLE001
        raise DataSourceError(f"拉取股票清单失败: {exc}") from exc
    return df.rename(columns={"code": "code", "name": "name"})
