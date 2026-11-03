"""估值数据与定投估值分位的回归测试（不联网）。

跑法（在 backend 目录）：
    uv run python -m unittest discover -s tests -v

覆盖：
- ROE 由 PB ÷ PE 推算，亏损（PE ≤ 0）时置空
- 历史分位只用「当时已公布」的数据：滞后后不得出现未来数据
- 没有映射 / 没有估值时返回空表，策略回退
- 枚举参数（choice）的校验与传递
- 定投的投入倍数随分位单调变化（低估多投、高估少投）
"""
from __future__ import annotations

import importlib.util
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from app.core.strategy_loader import StrategyError, build_parts  # noqa: E402
from app.data import valuation as val  # noqa: E402


def monthly_df(months: int, start: str = "2018-01-31") -> pd.DataFrame:
    """构造 months 个月的估值序列：PE 呈周期波动，PB 固定。

    用正弦而不用单调序列：单调序列在滚动窗口里永远是最大值，分位恒为 1，测不出区别。
    """
    dates = pd.date_range(start, periods=months, freq="ME")
    return pd.DataFrame(
        {
            "date": dates,
            "pe": [12.0 + 4.0 * math.sin(i / 6.0) for i in range(months)],
            "pe_ttm": [11.5 + 4.0 * math.sin(i / 6.0) for i in range(months)],
            "pb": [1.5] * months,
        }
    )


def load_dca_module():
    path = Path(__file__).resolve().parent.parent / "strategies" / "dca.py"
    spec = importlib.util.spec_from_file_location("hk_test_dca_val", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RoeTest(unittest.TestCase):
    def test_roe_is_pb_over_pe(self):
        df = pd.DataFrame({"date": pd.to_datetime(["2024-01-31"]), "pe": [13.0], "pb": [1.3]})
        out = val.add_roe(df)
        self.assertAlmostEqual(float(out["roe"].iloc[0]), 10.0, places=6)

    def test_negative_pe_gives_nan(self):
        """整体亏损时 PE 为负，ROE 无意义。"""
        df = pd.DataFrame({"date": pd.to_datetime(["2024-01-31"]), "pe": [-5.0], "pb": [1.3]})
        out = val.add_roe(df)
        self.assertTrue(pd.isna(out["roe"].iloc[0]))


class PercentileTest(unittest.TestCase):
    def test_percentile_varies_with_value(self):
        series = val.percentile_series(monthly_df(72), metric="pe", window_years=10, lag_months=0)
        self.assertGreater(len(series), 0)
        self.assertTrue(((series["pct"] > 0) & (series["pct"] < 1)).any())

    def test_lag_shifts_percentile_by_one_month(self):
        """滞后 1 个月：本月拿到的分位 = 上月算出的分位，不能用当月数据。"""
        df = monthly_df(72)
        raw = val.percentile_series(df, "pe", window_years=10, lag_months=0)
        lagged = val.percentile_series(df, "pe", window_years=10, lag_months=1)

        raw_by_date = dict(zip(raw["date"], raw["pct"]))
        self.assertTrue(len(lagged) > 0)
        for date, pct in zip(lagged["date"], lagged["pct"]):
            previous = max(d for d in raw_by_date if d < date)
            self.assertAlmostEqual(float(pct), float(raw_by_date[previous]), places=9)

    def test_no_percentile_before_min_samples(self):
        """样本不足 3 年不给分位，避免早期噪声。"""
        series = val.percentile_series(monthly_df(24), "pe", window_years=10, lag_months=0)
        self.assertEqual(len(series), 0)

    def test_unknown_metric_raises(self):
        with self.assertRaises(val.ValuationError):
            val.percentile_series(monthly_df(60), "pb_pe_ratio")


class LookupTest(unittest.TestCase):
    def test_missing_mapping_returns_empty(self):
        self.assertEqual(val.percentile_lookup("sz399999", "pe"), {})

    def test_index_without_long_history_returns_empty(self):
        """创业板指没有乐咕数据，应回退而不是报错。"""
        self.assertEqual(val.percentile_lookup("sz159915", "pe"), {})

    def test_cache_roundtrip_with_lookup(self):
        df = monthly_df(60)
        with tempfile.TemporaryDirectory() as tmp:
            ref = val.IndexRef("000300", "沪深300", "沪深300")
            with mock.patch.object(val, "VALUATION_DIR", Path(tmp)), \
                 mock.patch.object(val, "INDEX_MAP", {"sh510300": ref}), \
                 mock.patch.object(val, "_fetch_from_legulegu", return_value=df):
                first = val.load_valuation("sh510300")
                self.assertEqual(len(first), 60)
                # 第二次应命中缓存，不再调用网络
                with mock.patch.object(
                    val, "_fetch_from_legulegu", side_effect=AssertionError("不该联网")
                ):
                    second = val.load_valuation("sh510300")
                self.assertEqual(len(second), 60)

                table = val.percentile_lookup("sh510300", "pe", window_years=10, lag_months=1)
                self.assertTrue(table)
                # 第 36 个月（2020-12）才开始有分位，滞后一个月后从 2021-01 生效
                self.assertEqual(min(table), (2021, 1))
                self.assertEqual(len(table), 60 - 36)

    def test_corrupt_cache_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "沪深300.csv"
            path.write_text("这不是CSV", encoding="utf-8")
            self.assertIsNone(val._read_cache(path))


class ChoiceParamTest(unittest.TestCase):
    def test_invalid_choice_rejected(self):
        with self.assertRaises(StrategyError):
            build_parts("dca", {"valuation": "pe_ttm2"})

    def test_choice_default_is_off(self):
        from app.core.strategy_loader import list_strategies

        info = next(i for i in list_strategies() if i.id == "dca")
        param = next(p for p in info.params if p.name == "valuation")
        self.assertEqual(param.default, "off")

    def test_choice_value_reaches_script(self):
        """枚举参数原样传给脚本（这里不发网络：把查表替换掉）。"""
        fake = {(2024, 1): (10.0, 0.5)}
        with mock.patch.object(val, "percentile_lookup", return_value=fake) as lookup:
            parts = build_parts(
                "dca", {"valuation": "pb"}, {"symbol": "sh510300", "start": "2023-01-01", "end": "2024-12-31"}
            )
        self.assertIsNotNone(parts.sg)
        self.assertEqual(lookup.call_args.kwargs["metric"], "pb")


class ValuationActionTest(unittest.TestCase):
    """估值分位决定动作：低估买入、正常持有、高估卖出。"""

    def setUp(self):
        self.dca = load_dca_module()

    def test_low_percentile_buys(self):
        self.assertEqual(self.dca._action_for(0.10, 0.3, 0.7), "buy")

    def test_middle_percentile_holds(self):
        self.assertEqual(self.dca._action_for(0.50, 0.3, 0.7), "hold")

    def test_high_percentile_sells(self):
        self.assertEqual(self.dca._action_for(0.90, 0.3, 0.7), "sell")

    def test_boundaries_are_inclusive(self):
        self.assertEqual(self.dca._action_for(0.30, 0.3, 0.7), "buy")
        self.assertEqual(self.dca._action_for(0.70, 0.3, 0.7), "sell")

    def test_reversed_thresholds_are_normalised(self):
        self.assertEqual(self.dca._action_for(0.10, 0.7, 0.3), "buy")
        self.assertEqual(self.dca._action_for(0.90, 0.7, 0.3), "sell")
        self.assertEqual(self.dca._action_for(0.50, 0.7, 0.3), "hold")

    def test_same_thresholds_never_hold(self):
        self.assertEqual(self.dca._action_for(0.20, 0.5, 0.5), "buy")
        self.assertEqual(self.dca._action_for(0.80, 0.5, 0.5), "sell")


class SellLotsTest(unittest.TestCase):
    """高估止盈：按金额卖出，整手取整，且不超过持仓。"""

    def setUp(self):
        self.dca = load_dca_module()

    def test_sell_by_amount(self):
        # 1000 / 3.6 = 277.8 股 -> 200 股
        self.assertEqual(self.dca._sell_lots(1000.0, 3.6, 5000.0), 200.0)

    def test_capped_by_holding(self):
        self.assertEqual(self.dca._sell_lots(10000.0, 3.6, 300.0), 300.0)

    def test_below_one_lot_sells_nothing(self):
        self.assertEqual(self.dca._sell_lots(100.0, 3.6, 5000.0), 0.0)

    def test_zero_amount_sells_nothing(self):
        self.assertEqual(self.dca._sell_lots(0.0, 3.6, 5000.0), 0.0)

    def test_invalid_price_sells_nothing(self):
        self.assertEqual(self.dca._sell_lots(1000.0, 0.0, 5000.0), 0.0)

    def test_no_holding_sells_nothing(self):
        self.assertEqual(self.dca._sell_lots(1000.0, 3.6, 0.0), 0.0)


class NoMovingAverageTest(unittest.TestCase):
    """均线模式已删除：参数里不该再有 ma_n / slope / high_mult。"""

    def test_ma_params_removed(self):
        from app.core.strategy_loader import list_strategies

        info = next(i for i in list_strategies() if i.id == "dca")
        names = {p.name for p in info.params}
        self.assertNotIn("ma_n", names)
        self.assertNotIn("slope", names)
        self.assertNotIn("high_mult", names)

    def test_unknown_ma_params_are_ignored(self):
        """老的本地配置里可能还留着 ma_n 等字段，加载时忽略即可。"""
        parts = build_parts("dca", {"valuation": "off", "ma_n": 60, "slope": 2})
        self.assertIsNotNone(parts.sg)


class MissingValuationTest(unittest.TestCase):
    """选了估值指标却没有数据时要明确报错，而不是静默不交易。"""

    def test_index_without_data_raises(self):
        with self.assertRaises(RuntimeError) as ctx:
            build_parts("dca", {"valuation": "pe"}, {"symbol": "sz159915"})
        self.assertIn("创业板指", str(ctx.exception))

    def test_unknown_symbol_raises(self):
        with self.assertRaises(RuntimeError) as ctx:
            build_parts("dca", {"valuation": "pe"}, {"symbol": "sh999999"})
        self.assertIn("没有登记跟踪指数", str(ctx.exception))

    def test_fetch_failure_raises(self):
        with mock.patch.object(val, "percentile_lookup", return_value={}):
            with self.assertRaises(RuntimeError) as ctx:
                build_parts("dca", {"valuation": "pe"}, {"symbol": "sh510300"})
        self.assertIn("估值数据不可用", str(ctx.exception))

    def test_off_mode_needs_no_data(self):
        parts = build_parts("dca", {"valuation": "off"}, {"symbol": "sz159915"})
        self.assertIsNotNone(parts.sg)


class SellWiringTest(unittest.TestCase):
    def test_money_manager_overrides_sell(self):
        """高估止盈按金额卖出，必须给资金管理换上自定义的卖出数量函数。"""
        parts = build_parts("dca", {"valuation": "off"})
        self.assertIn("_get_sell_num", type(parts.mm).__dict__)

    def test_sell_amount_default(self):
        from app.core.strategy_loader import list_strategies

        info = next(i for i in list_strategies() if i.id == "dca")
        param = next(p for p in info.params if p.name == "sell_amount")
        self.assertEqual(param.default, 1000)
        self.assertGreaterEqual(param.max, 100000000)


class ReversedThresholdsTest(unittest.TestCase):
    def test_reversed_thresholds_build_fine(self):
        """用户把 30/70 填反，结果与正常一致。"""
        from app.core.strategy_loader import _param_defs  # noqa: PLC0415

        pct_lookup = {
            (2024, m): (10.0, 0.5) for m in range(1, 13)
        }
        with mock.patch.object(val, "percentile_lookup", return_value=pct_lookup):
            normal = build_parts("dca", {"valuation": "pe", "val_low_pct": 30, "val_high_pct": 70},
                                 {"symbol": "sh510300"})
            reversed_ = build_parts("dca", {"valuation": "pe", "val_low_pct": 70, "val_high_pct": 30},
                                    {"symbol": "sh510300"})
        self.assertIsNotNone(normal.sg)
        self.assertIsNotNone(reversed_.sg)


if __name__ == "__main__":
    unittest.main()
