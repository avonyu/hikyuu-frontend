#!/usr/bin/env python
"""修复已导入标的的名称（从数据源补齐）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.data.bootstrap import registered_symbols
from app.data.importer import create_stock_db, register_stock, StockMeta
from app.config import STOCK_DB


def main() -> int:
    from app.data.sources import list_etf, list_index, list_stock
    from app.data import catalog

    conn = create_stock_db(STOCK_DB)
    try:
        for entry in registered_symbols():
            name = entry["name"]
            if not name:
                kind = entry["kind"]
                try:
                    if kind == "INDEX":
                        df = list_index()
                    elif kind == "ETF":
                        df = list_etf()
                    else:
                        df = list_stock()
                    hit = df[df["code"].astype(str).str.zfill(6) == entry["code"]]
                    name = str(hit.iloc[0]["name"]) if not hit.empty else entry["code"]
                except Exception as exc:  # noqa: BLE001
                    print(f"  ! {entry['symbol']} 名称获取失败: {exc}")
                    name = entry["code"]

                register_stock(
                    conn,
                    StockMeta(entry["market"], entry["code"], name, entry["kind"]),
                )
                # Stock 表的 name 已存在时不会更新，需要直接改
                conn.execute(
                    "UPDATE Stock SET name=? WHERE marketid=? AND code=?",
                    (name, {"SH": 1, "SZ": 2, "BJ": 3}[entry["market"]], entry["code"]),
                )
                conn.commit()
                catalog.upsert(
                    entry["symbol"], entry["market"], entry["code"], name, entry["kind"]
                )
                print(f"  ✓ {entry['symbol']} → {name}")
            else:
                print(f"  - {entry['symbol']} 已有名称 {name}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
