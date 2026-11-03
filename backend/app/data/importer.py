"""写入 Hikyuu 的 HDF5 行情库与 SQLite 证券元数据库。

Hikyuu 的官方数据通道（TDX / pytdx）目前已失效——实测 104 个服务器中
23 个可连接、但 0 个能返回 K 线数据，因此行情需自行导入。

HDF5 表结构必须与 hikyuu.data.common_h5.H5Record 保持一致：
- 价格字段存的是「实际价格 × 1000」的整数
- datetime 格式为 YYYYMMDDHHMMSS
- transAmount 是「成交额 × 0.001」
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import tables as tb


# 统一的日线列顺序（与 sources.COLUMNS 一致）
KDATA_COLUMNS = ["open", "high", "low", "close", "volume", "amount"]


class H5Record(tb.IsDescription):
    """必须与 hikyuu.data.common_h5.H5Record 字段与类型完全一致。"""

    datetime = tb.UInt64Col()
    openPrice = tb.UInt32Col()
    highPrice = tb.UInt32Col()
    lowPrice = tb.UInt32Col()
    closePrice = tb.UInt32Col()
    transAmount = tb.UInt64Col()
    transCount = tb.UInt64Col()


# 与 Hikyuu StockTypeInfo 表的 type 字段对齐
STKTYPE = {
    "A": 1,
    "STOCK": 1,  # 本项目对 A 股的统一叫法，与 Hikyuu 的 A 股同一类型
    "INDEX": 2,
    "ETF": 5,
    "GEM": 8,
    "A_BJ": 11,
}

MARKET_ID = {"SH": 1, "SZ": 2, "BJ": 3}


@dataclass
class StockMeta:
    market: str      # SH / SZ / BJ
    code: str        # 6 位代码
    name: str
    kind: str        # A / INDEX / ETF / GEM / A_BJ


def _open_h5(path: Path):
    """打开或创建 HDF5 文件，返回 (handle, data_group)。

    注意：必须用 "a" 模式追加，否则会清空同一文件里其它标的的数据。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        handle = tb.open_file(path, "a")
        try:
            group = handle.get_node("/", "data")
        except Exception:  # noqa: BLE001
            group = handle.create_group("/", "data")
    else:
        handle = tb.open_file(path, "w")
        group = handle.create_group("/", "data")
    return handle, group


def read_kdata(path: Path, market: str, code: str) -> pd.DataFrame | None:
    """读回某个标的的日线，还原成与写入前一致的 DataFrame。

    价格 /1000、成交额 *1000、成交量取整，和 write_kdata 的量化互逆，
    所以「读出再写回」不会让数值漂移。
    """
    if not path.exists():
        return None
    handle = tb.open_file(path, "r")
    try:
        try:
            group = handle.get_node("/", "data")
            table = handle.get_node(group, market.upper() + code)
        except tb.NoSuchNodeError:
            return None
        if table.nrows == 0:
            return None

        dates = []
        rows = []
        for record in table.iterrows():
            stamp = int(record["datetime"])
            dates.append(
                pd.Timestamp(
                    year=stamp // 10**8,
                    month=stamp // 10**6 % 100,
                    day=stamp // 10**4 % 100,
                )
            )
            rows.append(
                {
                    "open": int(record["openPrice"]) / 1000,
                    "high": int(record["highPrice"]) / 1000,
                    "low": int(record["lowPrice"]) / 1000,
                    "close": int(record["closePrice"]) / 1000,
                    "volume": float(int(record["transCount"])),
                    "amount": float(int(record["transAmount"])) * 1000,
                }
            )
        df = pd.DataFrame(rows, index=pd.DatetimeIndex(dates), columns=KDATA_COLUMNS)
        return df.sort_index()
    finally:
        handle.close()


def merge_kdata(existing: pd.DataFrame, fresh: pd.DataFrame) -> pd.DataFrame:
    """按日期合并两段日线；同一天以 fresh 为准，返回升序结果。"""
    merged = pd.concat([existing, fresh])
    merged = merged[~merged.index.duplicated(keep="last")]
    return merged.sort_index()


def kdata_bounds(path: Path, market: str, code: str) -> tuple[str, str] | None:
    """读取某标的的首末日期（YYYY-MM-DD），只碰两行，不解析整表。"""
    if not path.exists():
        return None
    handle = tb.open_file(path, "r")
    try:
        try:
            group = handle.get_node("/", "data")
            table = handle.get_node(group, market.upper() + code)
        except tb.NoSuchNodeError:
            return None
        if table.nrows == 0:
            return None

        def fmt(stamp: int) -> str:
            return f"{stamp // 10**8:04d}-{stamp // 10**6 % 100:02d}-{stamp // 10**4 % 100:02d}"

        return fmt(int(table[0]["datetime"])), fmt(int(table[-1]["datetime"]))
    finally:
        handle.close()


def write_kdata(path: Path, market: str, code: str, df: pd.DataFrame,
                merge: bool = False) -> int:
    """写入单个标的的日线，返回写入后该表的总行数。

    df 要求 index 为 DatetimeIndex，列为 open/high/low/close/volume/amount。
    merge=True 时先读回已有数据、按日期合并（新数据覆盖同一天），再整表重写，
    因此可以安全地用于增量更新。
    """
    if merge:
        existing = read_kdata(path, market, code)
        if existing is not None and not existing.empty:
            df = merge_kdata(existing, df)

    handle, group = _open_h5(path)
    table_name = market.upper() + code
    try:
        handle.remove_node(group, table_name)
    except Exception:  # noqa: BLE001 - 表不存在
        pass

    table = handle.create_table(group, table_name, H5Record)
    row = table.row
    for date, record in df.iterrows():
        # datetime 用具名字段赋值：PyTables 会按字母序重排列，位置传 tuple 会错位
        row["datetime"] = int(
            (date.year * 10000 + date.month * 100 + date.day) * 10000
        )
        row["openPrice"] = int(round(float(record["open"]) * 1000))
        row["highPrice"] = int(round(float(record["high"]) * 1000))
        row["lowPrice"] = int(round(float(record["low"]) * 1000))
        row["closePrice"] = int(round(float(record["close"]) * 1000))
        row["transAmount"] = int(round(float(record.get("amount", 0.0) or 0.0) * 0.001))
        row["transCount"] = int(float(record.get("volume", 0.0) or 0.0))
        row.append()

    table.flush()
    count = table.nrows
    handle.flush()
    handle.close()
    return count


def create_stock_db(db_path: Path) -> sqlite3.Connection:
    """创建（或打开）Hikyuu 的证券元数据库。"""
    from hikyuu.data.common_sqlite3 import create_database

    db_path.parent.mkdir(parents=True, exist_ok=True)
    fresh = not db_path.exists()
    conn = sqlite3.connect(db_path)
    if fresh:
        create_database(conn)
        conn.commit()
    return conn


def register_stock(conn: sqlite3.Connection, meta: StockMeta) -> int:
    """把证券登记进 Stock 表，返回 stockid。已存在则直接返回原 id。"""
    market_id = MARKET_ID[meta.market]
    cur = conn.execute(
        "SELECT stockid FROM Stock WHERE marketid=? AND code=?", (market_id, meta.code)
    )
    row = cur.fetchone()
    if row:
        return int(row[0])

    stock_id = conn.execute("SELECT COALESCE(MAX(stockid),0)+1 FROM Stock").fetchone()[0]
    conn.execute(
        "INSERT INTO Stock (stockid, marketid, code, name, type, valid, startDate, endDate)"
        " VALUES (?,?,?,?,?,1,19901219,20500101)",
        (stock_id, market_id, meta.code, meta.name, STKTYPE[meta.kind]),
    )
    conn.commit()
    return int(stock_id)


def list_registered(conn: sqlite3.Connection) -> list[dict]:
    """列出已登记的证券。"""
    rows = conn.execute(
        "SELECT s.stockid, m.market, s.code, s.name, s.type FROM Stock s"
        " JOIN Market m ON s.marketid = m.marketid ORDER BY s.marketid, s.code"
    ).fetchall()
    type_names = {v: k for k, v in STKTYPE.items()}
    return [
        {
            "stock_id": int(r[0]),
            "market": r[1],
            "code": r[2],
            "name": r[3],
            "kind": type_names.get(int(r[4]), "A"),
            "symbol": f"{r[1].lower()}{r[2]}",
        }
        for r in rows
    ]
