"""本地标的清单与增量状态。

清单缓存在本地 JSON，避免每次打开前端都去打外网（akshare 的全市场
ETF 清单接口实测需 32s）。
"""
from __future__ import annotations

import json
from pathlib import Path

from app.config import CFG_DIR

CATALOG_FILE = CFG_DIR / "catalog.json"

# 常见宽基 ETF，作为首次使用的默认标的
DEFAULT_ETFS = [
    ("SH", "510300", "沪深300ETF"),
    ("SH", "510500", "中证500ETF"),
    ("SH", "510050", "上证50ETF"),
    ("SZ", "159915", "创业板ETF"),
    ("SH", "588000", "科创50ETF"),
    ("SZ", "159919", "沪深300ETF"),
]


def _read() -> dict:
    if not CATALOG_FILE.exists():
        return {}
    try:
        return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write(data: dict) -> None:
    CFG_DIR.mkdir(parents=True, exist_ok=True)
    CATALOG_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_entries() -> dict[str, dict]:
    """symbol -> {market, code, name, kind, last_date}"""
    return _read().get("symbols", {})


def get_symbol(symbol: str) -> dict | None:
    return get_entries().get(symbol.lower())


def upsert(symbol: str, market: str, code: str, name: str, kind: str,
           last_date: str | None = None) -> None:
    data = _read()
    symbols = data.setdefault("symbols", {})
    key = symbol.lower()
    entry = symbols.get(key, {})
    entry.update({"market": market, "code": code, "name": name, "kind": kind})
    if last_date:
        entry["last_date"] = last_date
    symbols[key] = entry
    _write(data)


def set_last_date(symbol: str, last_date: str) -> None:
    data = _read()
    symbols = data.setdefault("symbols", {})
    key = symbol.lower()
    if key in symbols:
        symbols[key]["last_date"] = last_date
        _write(data)


def remove(symbol: str) -> None:
    data = _read()
    symbols = data.setdefault("symbols", {})
    symbols.pop(symbol.lower(), None)
    _write(data)


def list_all() -> list[dict]:
    """按代码排序的清单列表。"""
    entries = get_entries()
    return [
        {"symbol": sym, **meta}
        for sym, meta in sorted(entries.items())
    ]
