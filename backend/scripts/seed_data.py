#!/usr/bin/env python
"""初始化数据：拉取行情写入 Hikyuu 的 HDF5 库。

用法:
    uv run python scripts/seed_data.py --symbols sh510300,sh510500
    uv run python scripts/seed_data.py --symbols sh510300 --incremental
    uv run python scripts/seed_data.py --defaults
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.data.bootstrap import seed_all
from app.data.catalog import DEFAULT_ETFS


def parse_symbols(raw: str) -> list[tuple[str, str, str, str]]:
    """把 'sh510300' 解析成 (market, code, name, kind)。

    名称未知时留空，导入后由调用方补齐。
    """
    out = []
    for item in raw.split(","):
        item = item.strip().lower()
        if not item:
            continue
        if item.startswith(("sh", "sz", "bj")):
            market, code = item[:2].upper(), item[2:]
        else:
            market, code = "SH", item
        out.append((market, code, "", "ETF"))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化回测数据")
    parser.add_argument("--symbols", default="", help="逗号分隔的标的，如 sh510300,sh510500")
    parser.add_argument("--start", default="20180101", help="起始日期 YYYYMMDD")
    parser.add_argument("--end", default="20241231", help="结束日期 YYYYMMDD")
    parser.add_argument("--incremental", action="store_true", help="只补拉缺口数据")
    parser.add_argument("--defaults", action="store_true", help="额外导入默认 ETF 列表")
    args = parser.parse_args()

    symbols = parse_symbols(args.symbols)
    if args.defaults:
        symbols += [(m, c, n, "ETF") for m, c, n in DEFAULT_ETFS]
    if not symbols:
        symbols += [(m, c, n, "ETF") for m, c, n in DEFAULT_ETFS]

    print(f"准备导入 {len(symbols)} 个标的 …")
    results = seed_all(symbols, start=args.start, end=args.end, incremental=args.incremental)

    print()
    failed = 0
    for r in results:
        if r.error:
            failed += 1
            print(f"  ✗ {r.symbol:12s} {r.error}")
        elif r.skipped:
            print(f"  - {r.symbol:12s} 无新数据")
        else:
            print(f"  ✓ {r.symbol:12s} {r.rows:>6d} 根  {r.first_date} ~ {r.last_date}")

    if failed:
        print(f"\n{failed} 个标的导入失败")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
