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
| `build(params)` | **是** | 返回 Hikyuu 的信号发生器（`SG_*`）实例 |

`params` 已经按 `PARAMS` 做过类型转换与范围校验：

- `default` 是 `int` → 传进来就是 `int`（`MA(n=5)` 不会收到 `5.0`）；
- `default` 是 `float` → 传 `float`；
- 超出 `min`/`max` 会直接报错，不会静默夹取。

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
```

指标用**未绑定**的 `CLOSE()` 即可，`SYS_Simple.run()` 会自动绑定到 K 线；指标之间支持 `+ - * /` 和比较运算（比较结果是 0/1 指标，可直接喂 `SG_Bool`）。

## 注意

- 脚本在**后端进程内执行**，等价于给自己开了一个代码执行入口——只放自己信任的代码，别从网上直接拷。
- 导入失败的脚本不会拖垮服务，`GET /api/strategies` 会带 `error` 字段，界面上也能看到。
- 资金管理、止损/止盈、滑点仍然由界面上的表单控制，不在这里定义。
