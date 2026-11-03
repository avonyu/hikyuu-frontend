"""本地标的清单与增量状态。

清单缓存在本地 JSON，避免每次打开前端都去打外网（akshare 的全市场
ETF 清单接口实测需 32s）。
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid

from app.config import CFG_DIR

CATALOG_FILE = CFG_DIR / "catalog.json"

# 读-改-写必须串行：刷新接口在线程池里并发执行，不加锁会互相覆盖
_lock = threading.RLock()

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
    except json.JSONDecodeError:
        # 文件损坏：先留一份备份再当空清单处理，否则下一次写入会把现场一并覆盖掉。
        # 读文件本身失败（OSError，如被占用）则直接抛出，不能当成空清单去覆盖写。
        backup = CATALOG_FILE.with_name(f"catalog.corrupt-{int(time.time())}.json")
        try:
            os.replace(CATALOG_FILE, backup)
        except OSError:
            pass
        return {}


def _write(data: dict) -> None:
    """原子写入：先写临时文件再替换，写到一半崩溃也不会留下半截 JSON。"""
    CFG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CATALOG_FILE.with_name(f"{CATALOG_FILE.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, CATALOG_FILE)
    finally:
        tmp.unlink(missing_ok=True)


def get_entries() -> dict[str, dict]:
    """symbol -> {market, code, name, kind, last_date}"""
    with _lock:
        return _read().get("symbols", {})


def get_symbol(symbol: str) -> dict | None:
    return get_entries().get(symbol.lower())


def upsert(symbol: str, market: str, code: str, name: str, kind: str,
           last_date: str | None = None) -> None:
    with _lock:
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
    with _lock:
        data = _read()
        symbols = data.setdefault("symbols", {})
        key = symbol.lower()
        if key in symbols:
            symbols[key]["last_date"] = last_date
            _write(data)


def remove(symbol: str) -> None:
    with _lock:
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
