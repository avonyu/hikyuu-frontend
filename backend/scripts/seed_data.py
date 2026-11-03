#!/usr/bin/env python
"""初始化数据：拉取行情写入 Hikyuu 的 HDF5 库。

标的写法：市场前缀 + 6 位代码，如 sh510300 / sz399006。
无前缀时按代码段推断市场；000 段（沪市指数 vs 深市股票）有歧义，必须写前缀。
类别（ETF / STOCK / INDEX）默认按代码段自动判定，可用 --kind 覆盖。

用法:
    uv run python scripts/seed_data.py --symbols sh510300,sh510500
    uv run python scripts/seed_data.py --symbols sh600519,sz000001
    uv run python scripts/seed_data.py --symbols sz399006 --kind INDEX
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
from app.data.kinds import (
    KINDS,
    KindError,
    infer_market,
    normalize_code,
    resolve_kind,
)


def parse_symbols(raw: str) -> list[tuple[str, str]]:
    """把 'sh510300,sz399006' 解析成 [(market, code)]。

    无前缀时按代码段推断市场；000 段有歧义，直接报错要求写前缀。
    """
    out: list[tuple[str, str]] = []
    for item in raw.split(","):
        item = item.strip().lower()
        if not item:
            continue
        if item[:2] in ("sh", "sz", "bj"):
            market, code = item[:2].upper(), item[2:]
        else:
            code = item
            market = infer_market(code)
            if market is None:
                raise KindError(
                    f"无法从 {item} 判断市场（000xxx 沪市是指数、深市是股票），"
                    "请写成 sh000001 / sz000001"
                )
        out.append((market, normalize_code(code)))
    return out


def main() -> int:
    # Windows 控制台默认 GBK，直接 print ✓/✗ 会 UnicodeEncodeError
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="初始化回测数据")
    parser.add_argument("--symbols", default="", help="逗号分隔的标的，如 sh510300,sh600519")
    parser.add_argument(
        "--kind",
        default=None,
        type=str.upper,
        choices=list(KINDS),
        help="强制证券类别；默认按代码段自动判定",
    )
    parser.add_argument("--start", default="20180101", help="起始日期 YYYYMMDD")
    parser.add_argument("--end", default="20241231", help="结束日期 YYYYMMDD")
    parser.add_argument("--incremental", action="store_true", help="只补拉缺口数据")
    parser.add_argument("--defaults", action="store_true", help="额外导入默认 ETF 列表")
    args = parser.parse_args()

    symbols: list[tuple[str, str, str, str]] = []
    try:
        parsed = parse_symbols(args.symbols)
        for market, code in parsed:
            kind, reason = resolve_kind(market, code, args.kind)
            symbols.append((market, code, "", kind))
            print(f"  {market.lower()}{code} → {kind:<5s}（{reason}）")
    except KindError as exc:
        print(f"参数错误: {exc}")
        return 2

    if args.defaults:
        symbols += [(m, c, n, "ETF") for m, c, n in DEFAULT_ETFS]
    if not symbols:
        symbols += [(m, c, n, "ETF") for m, c, n in DEFAULT_ETFS]

    print(f"\n准备导入 {len(symbols)} 个标的 …")
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
