# 自定义策略脚本

把 `.py` 文件放在这个目录下，界面「策略」里选「自定义脚本」即可看到。**修改后不需要重启后端**，下一次回测会用新代码（按文件 mtime 缓存）。

## 最小模板

```python
NAME = "我的策略"
DESCRIPTION = "一句话说明"
PARAMS = [
    {"name": "n", "label": "周期", "default": 20, "min": 2, "max": 200},
]

def build(params):
    from hikyuu.core import SG_Cross
    from hikyuu.indicator import CLOSE, MA
    return SG_Cross(MA(CLOSE(), n=params["n"]), MA(CLOSE(), n=params["n"] * 2))
```

## 约定

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `NAME` | 否 | 界面显示名，缺省用文件名 |
| `DESCRIPTION` | 否 | 说明文字 |
| `PARAMS` | 否 | 参数声明，前端据此生成输入框 |
| `MONEY_MANAGER` | 否 | 置 `True` 表示脚本自带资金管理（界面会提示表单的设置不生效） |
| `build(params)` | **是** | 返回 Hikyuu 的信号发生器（`SG_*`）实例 |

`params` 已经按 `PARAMS` 做过类型转换与范围校验：

- `default` 是 `int` → 这是整数参数，传进来就是 `int`（`MA(n=5)` 不会收到 `5.0`），界面输入框只接受整数；
- `default` 是 `float`（写成 `2.0` 而不是 `2`）→ 这是小数参数，传 `float`，界面允许小数。
  **小数参数的默认值必须写成浮点数**：写成 `2` 会被当成整数参数，小数输入会被截断；
- 超出 `min`/`max` 会直接报错，不会静默夹取。

## 自带资金管理

有些策略（如「定期定投」）需要自己决定每期买多少，光有信号做不到。
这类脚本可以让 `build()` 返回一个字典，额外带上资金管理：

```python
MONEY_MANAGER = True

def build(params):
    from hikyuu.trade_sys import crtMM, crtSG

    def _calculate(self, kdata):
        for i in range(0, len(kdata), 20):
            self._add_buy_signal(kdata[i].datetime)

    def _get_buy_num(self, datetime, stock, price, risk, part):
        # 每期买 10000 元，按 100 股整手取整
        cash = self.tm.cash(datetime)
        return float(int(min(10000.0, cash) / price / 100) * 100)

    sg = crtSG(_calculate, name="SG_DCA")
    sg.set_param("alternate", False)     # 连续买入必须关掉信号交替
    mm = crtMM(_get_buy_num, name="MM_DCA")
    mm.support_mult_buy_sell = True      # 加仓必须允许在已有持仓时继续买
    return {"sg": sg, "mm": mm}
```

返回的字典支持这些键：

| 键 | 类型 | 说明 |
| --- | --- | --- |
| `sg` | `SignalBase` | **必需**，信号发生器 |
| `mm` | `MoneyManagerBase` | 资金管理，给了就不使用表单里的设置 |
| `pg` | `ProfitGoalBase` | 目标价（止盈），给了就不使用表单里的止盈 % |
| `tp` | `StoplossBase` | 移动止盈 |

只返回信号发生器（不返回字典）时，行为和以前完全一致：资金管理、止损/止盈、滑点都由界面上的表单控制。

## 可用组件

```python
from hikyuu.core import (
    SG_Cross,      # 两条线交叉
    SG_Single,     # 单线（上穿买、下穿卖）
    SG_Bool,       # 买/卖两个条件表达式
    SG_And, SG_Or, # 组合
    SG_Band,       # 区间
)
from hikyuu.indicator import (
    CLOSE, MA, EMA, RSI, MACD, STD, HHV, LLV, CROSS,
)
from hikyuu.trade_sys import (
    crtSG,         # 用 Python 函数写信号
    crtMM,         # 用 Python 函数写资金管理
    crtPG,         # 用 Python 函数写目标价
)
```

指标用**未绑定**的 `CLOSE()` 即可，`SYS_Simple.run()` 会自动绑定到 K 线；指标之间支持 `+ - * /` 和比较运算（比较结果是 0/1 指标，可直接喂 `SG_Bool`）。

## Hikyuu 3.0 的两个坑

写自定义信号 / 资金管理时会踩到：

- **信号交替**：`SignalBase` 的 `alternate` 默认是 `True`，连续的买入信号只保留第一个。
  定投这类「每期都买」的策略必须 `sg.set_param("alternate", False)`。
- **资金管理默认不加仓**：默认不允许在已有持仓时继续买入，
  需要 `mm.support_mult_buy_sell = True`。

## 注意

- 脚本在**后端进程内执行**，等价于给自己开了一个代码执行入口——只放自己信任的代码，别从网上直接拷。
- 导入失败的脚本不会拖垮服务，`GET /api/strategies` 会带 `error` 字段，界面上也能看到。
- 资金管理、止损/止盈、滑点仍然由界面上的表单控制，不在这里定义（脚本自带资金管理的情况除外）。

## 现成脚本

| 脚本 | 说明 |
| --- | --- |
| `ma_cross.py` | 双均线交叉 |
| `single_ma.py` | 单均线（收盘价上穿下穿均线） |
| `boll_breakout.py` | 布林带突破 |
| `rsi_reversal.py` | RSI 超买超卖 |
| `dca.py` | 定期定投（可叠加智能定投与止盈） |

