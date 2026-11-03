"""定投策略的回归测试（不联网）。

跑法（在 backend 目录）：
    uv run python -m unittest discover -s tests -v

覆盖：
- 策略脚本能被加载器识别（名称、参数、自带资金管理标记）
- 定投日：每 N 个交易日 / 每月首个交易日
- 买入信号与每期投入金额（100 股整手、不超过可用现金）
- 智能定投的投入倍数（低于均线多投、高于均线少投）
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.strategy_loader import build_parts, list_strategies  # noqa: E402

STRATEGY_ID = "dca"


def _load_strategy_module():
    """直接加载策略脚本（不经后端进程），方便单独测试。"""
    import importlib.util

    path = Path(__file__).resolve().parent.parent / "strategies" / f"{STRATEGY_ID}.py"
    spec = importlib.util.spec_from_file_location(f"hk_test_{STRATEGY_ID}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeBar:
    """最小 K 线记录替身，只提供策略用到的字段。"""

    def __init__(self, dt, close):
        self.datetime = dt
        self.close = close


class _FakeDatetime:
    """够用的 Datetime 替身：支持按日期比较与取年 / 月。"""

    def __init__(self, y: int, m: int, d: int):
        self.year = y
        self.month = m
        self.day = d
        self._key = (y, m, d)

    def __eq__(self, other):
        return isinstance(other, _FakeDatetime) and self._key == other._key

    def __lt__(self, other):
        return self._key < other._key

    def __le__(self, other):
        return self._key <= other._key

    def __gt__(self, other):
        return self._key > other._key

    def __ge__(self, other):
        return self._key >= other._key

    def __hash__(self):
        return hash(self._key)

    def __repr__(self):
        return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"


class BuyBarsTest(unittest.TestCase):
    def test_fixed_interval(self):
        """每 period 个交易日定投一次，从区间第一根 K 线开始。"""
        mod = _load_strategy_module()
        kdata = [_FakeBar(_FakeDatetime(2023, 1, 3 + i), 10.0) for i in range(10)]
        self.assertEqual(mod._buy_bars(kdata, 3), [0, 3, 6, 9])

    def test_monthly_first_trading_day(self):
        """每月只在首个交易日定投一次。"""
        mod = _load_strategy_module()
        kdata = [
            _FakeBar(_FakeDatetime(2023, 1, 3), 10.0),
            _FakeBar(_FakeDatetime(2023, 1, 4), 10.0),
            _FakeBar(_FakeDatetime(2023, 2, 1), 10.0),
            _FakeBar(_FakeDatetime(2023, 2, 2), 10.0),
            _FakeBar(_FakeDatetime(2023, 3, 1), 10.0),
        ]
        self.assertEqual(mod._buy_bars(kdata, 0), [0, 2, 4])


class LoaderTest(unittest.TestCase):
    def test_strategy_is_listed(self):
        """脚本能被加载器识别，并声明了参数与自带资金管理标记。"""
        infos = {info.id: info for info in list_strategies()}
        self.assertIn(STRATEGY_ID, infos)
        info = infos[STRATEGY_ID]
        self.assertIsNone(info.error)
        self.assertTrue(info.money_manager)
        names = {p.name for p in info.params}
        self.assertEqual(names, {"period", "amount", "ma_n", "slope", "low_mult", "high_mult"})

    def test_build_parts_returns_signal_and_money_manager(self):
        """build() 返回字典时，加载器要能拆出信号与资金管理。"""
        parts = build_parts(STRATEGY_ID, {"period": 10, "amount": 5000})
        self.assertIsNotNone(parts.sg)
        self.assertIsNotNone(parts.mm)
        self.assertIsNone(parts.pg)

    def test_signal_is_not_alternating(self):
        """定投每期都是买入，信号不能交替，否则连续买入会被吞掉。"""
        parts = build_parts(STRATEGY_ID, {"period": 10, "amount": 5000})
        self.assertFalse(parts.sg.get_param("alternate"))

    def test_money_manager_allows_multi_buy(self):
        """定投是加仓，资金管理必须允许在已有持仓时继续买入。"""
        parts = build_parts(STRATEGY_ID, {"period": 10, "amount": 5000})
        self.assertTrue(parts.mm.support_mult_buy_sell)

    def test_param_range_is_validated(self):
        """超出声明范围的参数要报错，不能静默夹取。"""
        from app.core.strategy_loader import StrategyError

        with self.assertRaises(StrategyError):
            build_parts(STRATEGY_ID, {"period": -1})
        with self.assertRaises(StrategyError):
            build_parts(STRATEGY_ID, {"amount": 1})


class BuySizeTest(unittest.TestCase):
    """资金管理：每期投入固定金额，按 100 股整手向下取整，且不超过可用现金。"""

    def _money_manager(self, **params):
        from hikyuu.core import crtTM

        base = {"period": 10, "amount": 10000, "ma_n": 0}
        base.update(params)
        parts = build_parts(STRATEGY_ID, base)
        parts.mm.tm = crtTM(init_cash=300000.0)
        return parts.mm

    def test_fixed_amount_is_lot_rounded(self):
        """每期投入固定金额，按 100 股整手向下取整。"""
        from hikyuu.core import Datetime

        mm = self._money_manager()
        # 10000 / 3.604 = 2774.6 → 2700 股
        self.assertEqual(
            mm._get_buy_num(Datetime(2023, 1, 3), None, 3.604, 1.0, None), 2700.0
        )
        # 10000 / 3.9 = 2564.1 → 2500 股
        self.assertEqual(
            mm._get_buy_num(Datetime(2023, 1, 3), None, 3.9, 1.0, None), 2500.0
        )

    def test_buy_size_never_exceeds_available_cash(self):
        """现金不足时不能透支，超买部分要砍掉。"""
        from hikyuu.core import Datetime, crtTM

        mm = self._money_manager(amount=100000)
        mm.tm = crtTM(init_cash=1000.0)
        # 可用 1000 元（再留 1% 手续费）→ 最多 990 元 → 990 / 10 = 99 股 → 不足 1 手
        self.assertEqual(
            mm._get_buy_num(Datetime(2023, 1, 3), None, 10.0, 1.0, None), 0.0
        )

    def test_buy_size_zero_when_price_invalid(self):
        from hikyuu.core import Datetime

        mm = self._money_manager()
        self.assertEqual(
            mm._get_buy_num(Datetime(2023, 1, 3), None, 0.0, 1.0, None), 0.0
        )


if __name__ == "__main__":
    unittest.main()
