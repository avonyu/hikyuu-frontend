"""本轮排查修复的回归测试（不联网）。

跑法（在 backend 目录）：
    uv run python -m unittest discover -s tests -v

覆盖：
- 请求里的日期格式、先后顺序在入口被拦下，不再让引擎抛 IndexError
- 前复权数据整体变化时能被识别（增量合并会留下价格断层）
- 坏数据（NaN / 负价）写入前就被拒绝，已有表保持完好
- 本地清单损坏时先备份，原子写入不留半截文件
- 策略参数拒绝 NaN / inf
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.api.schemas import BacktestRequest, OverlayQueryRequest  # noqa: E402
from app.core.strategy_loader import StrategyError, build_parts  # noqa: E402
from app.data import catalog  # noqa: E402
from app.data.importer import prices_diverged, read_kdata, write_kdata  # noqa: E402


def make_df(rows: dict[str, float]) -> pd.DataFrame:
    """{日期: 收盘价} -> 完整 K 线 DataFrame。"""
    index = pd.DatetimeIndex([pd.Timestamp(d) for d in rows])
    closes = list(rows.values())
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "volume": [1000.0] * len(closes),
            "amount": [1e6] * len(closes),
        },
        index=index,
    )


class DateValidationTest(unittest.TestCase):
    def _request(self, **over):
        body = {
            "symbol": "sh510300",
            "start": "2023-01-01",
            "end": "2024-12-31",
            "strategy": {"id": "ma_cross"},
        }
        body.update(over)
        return BacktestRequest(**body)

    def test_accepts_valid_range(self):
        req = self._request()
        self.assertEqual((req.start, req.end), ("2023-01-01", "2024-12-31"))

    def test_rejects_malformed_date(self):
        # 注意 20230101 这种紧凑写法 fromisoformat 会接受并规范化，不算非法
        for bad in ("2023-13-45", "2023/01/01", "not-a-date", ""):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                self._request(start=bad)

    def test_rejects_reversed_range(self):
        with self.assertRaises(ValidationError) as ctx:
            self._request(start="2024-12-31", end="2023-01-01")
        self.assertIn("不能晚于", str(ctx.exception))

    def test_rejects_out_of_engine_range(self):
        with self.assertRaises(ValidationError):
            self._request(start="1980-01-01")

    def test_overlay_query_validates_dates_too(self):
        with self.assertRaises(ValidationError):
            OverlayQueryRequest(symbol="sh510300", start="2024-12-31", end="2023-01-01")

    def test_risk_params_reject_nonsense(self):
        with self.assertRaises(ValidationError):
            self._request(stoploss=0)
        with self.assertRaises(ValidationError):
            self._request(slippage=2)  # 200% 滑点


class PriceAdjustTest(unittest.TestCase):
    def test_detects_refit_history(self):
        """除权后数据源整体重算历史价格：重叠日收盘价对不上。"""
        old = make_df({"2024-01-02": 10.0, "2024-01-03": 10.5})
        fresh = make_df({"2024-01-03": 8.4, "2024-01-04": 8.6})
        self.assertTrue(prices_diverged(old, fresh))

    def test_same_prices_are_continuous(self):
        old = make_df({"2024-01-02": 10.0, "2024-01-03": 10.5})
        fresh = make_df({"2024-01-03": 10.5, "2024-01-04": 10.6})
        self.assertFalse(prices_diverged(old, fresh))

    def test_quantization_noise_is_not_divergence(self):
        """库里价格只存 3 位小数，10.5004 与 10.5 不能算断层。"""
        old = make_df({"2024-01-03": 10.5})
        fresh = make_df({"2024-01-03": 10.5004})
        self.assertFalse(prices_diverged(old, fresh))

    def test_no_overlap(self):
        old = make_df({"2024-01-02": 10.0})
        fresh = make_df({"2024-01-05": 30.0})
        self.assertFalse(prices_diverged(old, fresh))


class WriteSafetyTest(unittest.TestCase):
    def test_nan_price_keeps_existing_data(self):
        """坏数据在写入前被拒，原有表格不被清空。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sh_day.h5"
            write_kdata(path, "SH", "510300", make_df({"2024-01-02": 10.0, "2024-01-03": 10.5}))

            bad = make_df({"2024-01-04": 11.0})
            bad.loc[bad.index[0], "close"] = float("nan")
            with self.assertRaises(ValueError):
                write_kdata(path, "SH", "510300", bad, merge=True)

            kept = read_kdata(path, "SH", "510300")
            self.assertEqual(list(kept.index.strftime("%Y-%m-%d")), ["2024-01-02", "2024-01-03"])

    def test_negative_price_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sh_day.h5"
            bad = make_df({"2024-01-02": 10.0})
            bad.loc[bad.index[0], "low"] = -1
            with self.assertRaises(ValueError):
                write_kdata(path, "SH", "510300", bad)

    def test_empty_frame_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                write_kdata(Path(tmp) / "sh_day.h5", "SH", "510300", pd.DataFrame())


class StockDbTest(unittest.TestCase):
    def test_creates_tables_when_file_missing(self):
        from app.data.importer import create_stock_db

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "stock.db"
            conn = create_stock_db(db)
            try:
                tables = {
                    r[0]
                    for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
            finally:
                conn.close()
            self.assertIn("Stock", tables)

    def test_empty_existing_file_is_repaired(self):
        """上次建库中途失败会留下空文件；不能因为文件存在就跳过建表。"""
        from app.data.importer import create_stock_db

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "stock.db"
            db.touch()
            conn = create_stock_db(db)
            try:
                self.assertIsNotNone(
                    conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='Stock'"
                    ).fetchone()
                )
            finally:
                conn.close()


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "catalog.json"
        self.patch = mock.patch.object(catalog, "CATALOG_FILE", self.path)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_upsert_then_read(self):
        catalog.upsert("SH510300", "SH", "510300", "沪深300ETF", "ETF", last_date="2024-12-31")
        self.assertEqual(catalog.get_symbol("sh510300")["name"], "沪深300ETF")
        # ll 写入后不残留临时文件
        self.assertEqual([p.name for p in Path(self.tmp.name).iterdir()], ["catalog.json"])

    def test_corrupt_file_is_backed_up(self):
        self.path.write_text("{ 不是 JSON", encoding="utf-8")
        self.assertEqual(catalog.get_entries(), {})
        backups = list(Path(self.tmp.name).glob("catalog.corrupt-*.json"))
        self.assertEqual(len(backups), 1)
        # 备份能读回原始内容，现场没有被丢掉
        self.assertIn("不是 JSON", backups[0].read_text(encoding="utf-8"))

        catalog.upsert("SH510300", "SH", "510300", "沪深300ETF", "ETF")
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["symbols"]["sh510300"]["code"], "510300")


class StrategyParamTest(unittest.TestCase):
    def test_nan_param_rejected(self):
        """JSON 里的 NaN 会让 float() 通过，必须在范围校验前拦下。"""
        with self.assertRaises(StrategyError):
            build_parts("ma_cross", {"fast": float("nan")})

    def test_infinite_param_rejected(self):
        with self.assertRaises(StrategyError):
            build_parts("ma_cross", {"slow": float("inf")})

    def test_unknown_param_is_ignored(self):
        """前端可能残留旧脚本的参数，多出来的一律忽略，不能报错。"""
        parts = build_parts("ma_cross", {"fast": 5, "slow": 20, "gone": 1})
        self.assertIsNotNone(parts.sg)


if __name__ == "__main__":
    unittest.main()
