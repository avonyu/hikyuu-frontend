"""HDF5 增量合并的回归测试（不联网）。

跑法（在 backend 目录）：
    uv run python -m unittest discover -s tests -v
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from app.data.importer import (  # noqa: E402
    kdata_bounds,
    merge_kdata,
    read_kdata,
    write_kdata,
)


def make_df(dates: list[str], base: float = 10.0) -> pd.DataFrame:
    index = pd.DatetimeIndex([pd.Timestamp(d) for d in dates])
    return pd.DataFrame(
        {
            "open": [base] * len(index),
            "high": [base + 1] * len(index),
            "low": [base - 1] * len(index),
            "close": [base + 0.5] * len(index),
            "volume": [1000.0] * len(index),
            "amount": [1e6] * len(index),
        },
        index=index,
    )


class MergeTest(unittest.TestCase):
    def test_incremental_keeps_history(self):
        """增量写入不应该丢历史（之前会因为整表重建被截断）。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sh_day.h5"
            write_kdata(path, "SH", "510300", make_df(
                ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
            ))
            self.assertEqual(read_kdata(path, "SH", "510300").shape[0], 4)

            total = write_kdata(
                path, "SH", "510300",
                make_df(["2024-01-05", "2024-01-08"], base=20.0),
                merge=True,
            )

            merged = read_kdata(path, "SH", "510300")
            self.assertEqual(total, 5)
            self.assertEqual(
                list(merged.index.strftime("%Y-%m-%d")),
                ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"],
            )
            # 重叠日以新数据为准
            self.assertAlmostEqual(float(merged.loc["2024-01-05", "close"]), 20.5, places=6)
            # 未覆盖的历史保持不变
            self.assertAlmostEqual(float(merged.loc["2024-01-02", "close"]), 10.5, places=6)

    def test_merge_is_idempotent(self):
        """重复合并同一段数据不会产生重复行，也不会让数值漂移。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sh_day.h5"
            df = make_df(["2024-01-02", "2024-01-03"])
            df.loc["2024-01-02", "amount"] = 2.576088e9
            df.loc["2024-01-02", "volume"] = 6563108.0
            write_kdata(path, "SH", "510300", df)

            for _ in range(3):
                write_kdata(path, "SH", "510300", df, merge=True)

            result = read_kdata(path, "SH", "510300")
            self.assertEqual(result.shape[0], 2)
            self.assertAlmostEqual(
                float(result.loc["2024-01-02", "amount"]), 2.576088e9, delta=500
            )
            self.assertAlmostEqual(
                float(result.loc["2024-01-02", "volume"]), 6563108.0, places=6
            )

    def test_empty_merge_falls_back_to_plain_write(self):
        """没有历史数据时，merge=True 等同于普通写入。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sh_day.h5"
            total = write_kdata(path, "SH", "510300", make_df(["2024-01-02"]), merge=True)
            self.assertEqual(total, 1)
            self.assertIsNone(read_kdata(path, "SH", "999999"))

    def test_merge_kdata_dedupes_and_sorts(self):
        old = make_df(["2024-01-03", "2024-01-02"])
        fresh = make_df(["2024-01-03", "2024-01-05"], base=30.0)
        merged = merge_kdata(old, fresh)
        self.assertEqual(
            list(merged.index.strftime("%Y-%m-%d")),
            ["2024-01-02", "2024-01-03", "2024-01-05"],
        )
        self.assertAlmostEqual(float(merged.loc["2024-01-03", "open"]), 30.0, places=6)

    def test_kdata_bounds(self):
        """落盘后的首末日期按表里实际内容算，供 catalog 记录 last_date。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sh_day.h5"
            write_kdata(path, "SH", "510300", make_df(
                ["2024-03-01", "2024-03-04", "2024-03-05"]
            ))
            self.assertEqual(kdata_bounds(path, "SH", "510300"), ("2024-03-01", "2024-03-05"))
            self.assertIsNone(kdata_bounds(path, "SH", "999999"))


if __name__ == "__main__":
    unittest.main()
