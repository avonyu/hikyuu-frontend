"""写入 Hikyuu 的 HDF5 行情库与 SQLite 证券元数据库。

Hikyuu 的官方数据通道（TDX / pytdx）目前已失效——实测 104 个服务器中
23 个可连接、但 0 个能返回 K 线数据，因此行情需自行导入。

HDF5 表结构必须与 hikyuu.data.common_h5.H5Record 保持一致：
- 价格字段存的是「实际价格 × 1000」的整数
- datetime 格式为 YYYYMMDDHHMMSS
- transAmount 是「成交额 × 0.001」
"""
from __future__ import annotations

import math
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


def prices_diverged(existing: pd.DataFrame, fresh: pd.DataFrame) -> bool:
    """重叠日期上，新旧收盘价是否对不上。

    数据源给的是前复权价：一旦发生除权，**所有历史价格**都会整体变化。
    此时只把新拉的尾部合并进去，会在接缝处留下价格断层（回测里表现为假的暴涨暴跌）。
    重叠日的收盘价对不上，就说明历史已被重新复权，需要整段重拉。

    库里价格只存 3 位小数，容差要大于量化误差：绝对 0.002 + 相对 0.05%。
    """
    overlap = existing.index.intersection(fresh.index)
    if len(overlap) == 0:
        return False
    old = existing.loc[overlap, "close"].astype(float)
    new = fresh.loc[overlap, "close"].astype(float)
    return bool(((old - new).abs() > 0.002 + 0.0005 * new.abs()).any())


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

    # 先把所有行转成整数记录：数据有问题（NaN、负价）在这里就抛出，
    # 此时还没碰 HDF5 文件，已有数据不会受损。
    records = _to_records(df)

    handle, group = _open_h5(path)
    table_name = market.upper() + code
    tmp_name = f"_tmp_{table_name}"
    try:
        # 写到临时表，写完再原子替换：中途失败（磁盘满、进程被杀）旧表原样保留
        if tmp_name in group:
            handle.remove_node(group, tmp_name)
        table = handle.create_table(group, tmp_name, H5Record)
        row = table.row
        for rec in records:
            # datetime 用具名字段赋值：PyTables 会按字母序重排列，位置传 tuple 会错位
            for field, value in rec.items():
                row[field] = value
            row.append()
        table.flush()
        count = table.nrows
        handle.move_node(table, newparent=group, newname=table_name, overwrite=True)
        handle.flush()
        return count
    except BaseException:
        if tmp_name in group:
            handle.remove_node(group, tmp_name)
        raise
    finally:
        handle.close()


def _to_records(df: pd.DataFrame) -> list[dict[str, int]]:
    """DataFrame -> H5Record 字段字典列表（价格 ×1000、成交额 ×0.001 的整数）。"""
    if df.empty:
        raise ValueError("没有可写入的行情数据")

    records = []
    for date, record in df.iterrows():
        prices = {k: float(record[k]) for k in ("open", "high", "low", "close")}
        bad = [k for k, v in prices.items() if not math.isfinite(v) or v < 0]
        if bad:
            raise ValueError(f"{date:%Y-%m-%d} 的 {'/'.join(bad)} 无效：{prices}")
        records.append(
            {
                "datetime": int((date.year * 10000 + date.month * 100 + date.day) * 10000),
                "openPrice": int(round(prices["open"] * 1000)),
                "highPrice": int(round(prices["high"] * 1000)),
                "lowPrice": int(round(prices["low"] * 1000)),
                "closePrice": int(round(prices["close"] * 1000)),
                "transAmount": int(round(_finite(record.get("amount")) * 0.001)),
                "transCount": int(_finite(record.get("volume"))),
            }
        )
    return records


def _finite(value) -> float:
    """成交量 / 成交额缺失或 NaN 时按 0 处理。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def create_stock_db(db_path: Path) -> sqlite3.Connection:
    """创建（或打开）Hikyuu 的证券元数据库。"""
    from hikyuu.data.common_sqlite3 import create_database

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    # 文件存在不代表表已建好：上次建库中途失败会留下空库，
    # 之后每条 SQL 都会报 "no such table"，这里统一补齐
    has_stock = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='Stock'"
    ).fetchone()
    if not has_stock:
        create_database(conn)
        conn.commit()
        # createdb.sql 只在「看起来是空库」时执行；半成品库补救不了，给出可操作的提示
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='Stock'"
        ).fetchone():
            conn.close()
            raise RuntimeError(
                f"证券库 {db_path} 结构不完整（缺少 Stock 表），请删除该文件后重新导入数据"
            )
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
