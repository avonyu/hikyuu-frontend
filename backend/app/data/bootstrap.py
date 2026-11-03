"""数据初始化与增量更新。

流程：拉取行情 → 写入 HDF5 → 注册到 SQLite → 更新本地清单。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from app.config import CALENDAR_INDEXES, H5_FILES, STOCK_DB
from app.data import catalog
from app.data.importer import (
    StockMeta,
    create_stock_db,
    list_registered,
    register_stock,
    write_kdata,
)
from app.data.sources import DataSourceError, fetch_any, fetch_incremental


@dataclass
class SeedResult:
    symbol: str
    name: str
    rows: int
    first_date: str | None
    last_date: str | None
    skipped: bool = False
    error: str | None = None


def _h5_path(market: str) -> Path:
    return H5_FILES[market]


def _resolve_name(market: str, code: str, name: str, kind: str) -> str:
    """名称未知时从清单接口补齐。"""
    if name:
        return name
    from app.data.sources import list_etf, list_index, list_stock

    try:
        if kind == "INDEX":
            df = list_index()
        elif kind == "ETF":
            df = list_etf()
        elif kind == "STOCK":
            df = list_stock()
        else:
            return f"{market}{code}"
        hit = df[df["code"].astype(str).str.zfill(6) == code]
        if not hit.empty:
            return str(hit.iloc[0]["name"])
    except Exception:  # noqa: BLE001 - 名称补齐失败不影响导入
        pass
    return f"{market}{code}"


def seed_symbol(market: str, code: str, name: str, kind: str,
                start: str = "20180101", end: str = "20241231",
                incremental: bool = False) -> SeedResult:
    """导入单个标的。incremental=True 时只补拉缺口数据。"""
    symbol = f"{market.lower()}{code}"
    conn = create_stock_db(STOCK_DB)
    try:
        existing = catalog.get_symbol(symbol)
        last_date = existing.get("last_date") if existing else None
        name = _resolve_name(market, code, name, kind)

        if incremental and last_date:
            df = fetch_incremental(market, code, kind, last_date, start, end)
        else:
            df = fetch_any(market, code, kind, start, end)

        if df.empty:
            return SeedResult(symbol, name, 0, None, None, skipped=True)

        rows = write_kdata(_h5_path(market), market, code, df)
        register_stock(conn, StockMeta(market, code, name, kind))

        first = df.index[0].strftime("%Y-%m-%d")
        last = df.index[-1].strftime("%Y-%m-%d")
        catalog.upsert(symbol, market, code, name, kind, last_date=last)
        return SeedResult(symbol, name, rows, first, last)
    except DataSourceError as exc:
        return SeedResult(symbol, name, 0, None, None, error=str(exc))
    except Exception as exc:  # noqa: BLE001 - 单个标的失败不应中断整批导入
        return SeedResult(symbol, name, 0, None, None, error=f"{type(exc).__name__}: {exc}")
    finally:
        conn.close()


def seed_calendar_indexes(start: str = "20180101", end: str = "20241231") -> list[SeedResult]:
    """导入市场主指数。

    Hikyuu 用市场主指数推导交易日历，缺少它会导致
    `get_trading_calendar()` 返回空、资金曲线取不到。
    """
    results = []
    for market, code, name in CALENDAR_INDEXES:
        results.append(seed_symbol(market, code, name, "INDEX", start, end))
    return results


def seed_all(symbols: list[tuple[str, str, str, str]],
             start: str = "20180101", end: str = "20241231",
             incremental: bool = False) -> list[SeedResult]:
    """导入指数日历 + 指定标的。symbols 项为 (market, code, name, kind)。"""
    results = seed_calendar_indexes(start, end)
    for market, code, name, kind in symbols:
        results.append(seed_symbol(market, code, name, kind, start, end, incremental))
    return results


def registered_symbols() -> list[dict]:
    """已登记到 SQLite 的证券（对应 Hikyuu 能加载的标的）。"""
    conn = create_stock_db(STOCK_DB)
    try:
        return list_registered(conn)
    finally:
        conn.close()


def kdata_last_date(symbol: str) -> str | None:
    """从 HDF5 读取某标的最后一根 K 线的日期。"""
    import tables as tb

    entry = catalog.get_symbol(symbol)
    if not entry:
        return None
    path = _h5_path(entry["market"])
    if not path.exists():
        return None
    handle = tb.open_file(path, "r")
    try:
        group = handle.get_node("/", "data")
        table = handle.get_node(group, entry["market"].upper() + entry["code"])
        if table.nrows == 0:
            return None
        stamp = int(table[-1]["datetime"])
        # 存的是 YYYYMMDD * 10000（即 YYYYMMDDHHMMSS），月和日别解错位
        return (
            f"{stamp // 10**8:04d}-"
            f"{stamp // 10**6 % 100:02d}-"
            f"{stamp // 10**4 % 100:02d}"
        )
    except Exception:  # noqa: BLE001
        return None
    finally:
        handle.close()
