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
| `StrategyForm` | 回测参数表单：标的、区间、费率、信号、资金管理、指标叠加（Checkbox 多选）、风控 |
| `KlineChart` | lightweight-charts v5，K 线 + 成交量 + 指标线 + 买卖点 |
| `EquityChart` | 资金曲线，含初始资金基准线 |
| `MetricsPanel` | 关键指标卡片 + 全部指标明细 |
| `TradeTable` | 成交明细，含逐笔费用 |
| `EngineBadge` | 顶栏引擎状态指示标志，轮询 `/api/health` 实时刷新 |

图表数据全部由后端计算，前端只负责渲染。

## 引擎状态

引擎（StockManager）在首次回测时才懒加载，因此顶栏指示标志通过 `useHealth`
每 2 秒轮询 `/api/health`，状态分为：`idle` 待加载、`loading` 加载中、
`ready` 就绪、`error` 加载失败；后端不可达时显示「服务未连接」。

## 回测设置持久化

表单配置由 zustand 的 `useConfigStore`（`src/lib/config-store.ts`）持有，
经 `persist` 中间件写入 `localStorage` 的 `hikyuu-backtest-config`，
刷新页面后参数还在。

- 只持久化表单配置，回测结果不存，每次重新计算；
- 重新挂载时用默认值补齐缺失字段，避免旧数据缺键；
- 持久化的标的若已从行情库删除，会自动退回第一个可交易标的。

## 指标叠加

勾选指标后**无需重跑回测**即可生效：前端调用 `POST /api/overlays`
（后端只算指标线、不跑回测，4~50ms），值与回测结果里的完全一致。

- MA / EMA 画在主图窗格，与价格同轴；
- RSI（0~100）、MACD（围绕 0）量纲不同，各占一个副窗格，避免撑坏价格轴；
- 配色按指标类型固定，实时增删指标时其它线的颜色不会错位。
