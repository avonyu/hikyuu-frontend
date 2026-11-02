# Hikyuu 回测前端 — 界面

React 19 + Vite 8 + TypeScript + Tailwind CSS 4，配合 bun 使用。

```bash
bun install
bun run dev      # http://localhost:5173
bun run build    # 生产构建
bun run lint     # oxlint
```

`/api` 请求由 Vite 代理到 `http://127.0.0.1:8000`，需先启动后端。

## 组件

| 组件 | 说明 |
| --- | --- |
| `StrategyForm` | 回测参数表单：标的、区间、费率、信号、资金管理、指标叠加、风控 |
| `KlineChart` | lightweight-charts v5，K 线 + 成交量 + 指标线 + 买卖点 |
| `EquityChart` | 资金曲线，含初始资金基准线 |
| `MetricsPanel` | 关键指标卡片 + 全部指标明细 |
| `TradeTable` | 成交明细，含逐笔费用 |

图表数据全部由后端计算，前端只负责渲染。
