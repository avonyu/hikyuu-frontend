import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  CandlestickChart,
  ChartLine,
  MousePointerClick,
  SlidersHorizontal,
  Table2,
  TriangleAlert,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { EngineBadge } from '@/components/EngineBadge'
import { ModeToggle } from '@/components/mode-toggle'
import {
  fetchMeta,
  fetchOverlays,
  fetchStrategies,
  fetchSymbols,
  pollJob,
  submitBacktest,
} from './lib/api'
import { useConfigStore } from './lib/config-store'
import { useHealth } from './lib/use-health'
import type { BacktestResult, Meta, StrategyInfo, SymbolInfo } from './lib/types'
import EquityChart from './components/EquityChart'
import KlineChart from './components/KlineChart'
import MetricsPanel from './components/MetricsPanel'
import StrategyForm from './components/StrategyForm'
import StrategyDrawer from './components/StrategyDrawer'
import TradeTable from './components/TradeTable'

export default function App() {
  // 回测设置持久化到 localStorage，刷新页面后参数还在
  const config = useConfigStore((s) => s.config)
  const updateConfig = useConfigStore((s) => s.update)
  const [symbols, setSymbols] = useState<SymbolInfo[]>([])
  const [strategies, setStrategies] = useState<StrategyInfo[]>([])
  const [meta, setMeta] = useState<Meta | null>(null)
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [overlays, setOverlays] = useState<Record<string, number[]>>({})
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 引擎状态单独轮询：它在首次回测时才懒加载，
  // 与其它初始化数据分开，失败时也不影响主流程
  const { state: engineState, health, refresh: refreshHealth } = useHealth()

  useEffect(() => {
    void (async () => {
      try {
        const [s, m, st] = await Promise.all([
          fetchSymbols(),
          fetchMeta(),
          fetchStrategies(),
        ])
        setSymbols(s)
        setMeta(m)
        setStrategies(st)
        // 持久化的脚本已被改名或删除时，回退到第一个可用脚本
        const usable = st.filter((x) => !x.error)
        const picked = useConfigStore.getState().config.strategyId
        if (usable.length > 0 && !usable.some((x) => x.id === picked)) {
          const first = usable[0]
          updateConfig({ strategyId: first.id, strategyParams: {} })
        }
        // 持久化的标的可能已被删除，此时退回第一个可交易标的
        const tradable = s.filter((x) => x.kind !== 'INDEX')
        const current = useConfigStore.getState().config
        const kept = tradable.find((x) => x.symbol === current.symbol)
        if (!kept && tradable.length > 0) {
          updateConfig({ symbol: tradable[0].symbol })
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : '无法连接后端服务')
      }
    })()
  }, [updateConfig])

  // 叠加线：勾选变化时按「当前图上的标的与区间」实时重算
  useEffect(() => {
    if (!result) return
    // 合并连续勾选（如一口气勾三个），只发一次请求
    const timer = setTimeout(() => {
      void fetchOverlays({
        symbol: result.symbol,
        start: result.start,
        end: result.end,
        overlays: config.overlays,
      })
        .then(setOverlays)
        .catch(() => undefined)
    }, 150)
    return () => clearTimeout(timer)
  }, [config.overlays, result])

  const run = useCallback(async () => {
    setRunning(true)
    setError(null)
    // 脚本可能刚被修改：回测前刷新脚本列表，名称、说明与参数声明随之更新
    void fetchStrategies().then(setStrategies).catch(() => undefined)
    try {
      const { id } = await submitBacktest({
        symbol: config.symbol,
        start: config.start,
        end: config.end,
        init_cash: config.init_cash,
        cost_model: config.cost_model,
        strategy: { id: config.strategyId, params: config.strategyParams },
        money: {
          type: config.moneyType,
          n: config.count,
          percent: config.percent,
        },
        overlays: config.overlays.map((o) => ({ type: o.type, n: o.n })),
        stoploss: config.stoploss,
        takeprofit: config.takeprofit,
        slippage: config.slippage,
      })

      const job = await pollJob(id)
      if (job.status === 'error') {
        setError(job.error ?? '回测失败')
      } else if (job.result) {
        setResult(job.result)
        // 回测自带一份叠加线，先用上，再由下面的实时请求接管
        setOverlays(job.result.overlays)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '回测失败')
    } finally {
      setRunning(false)
      // 回测会触发引擎加载/复用，立即同步一次引擎状态
      void refreshHealth()
    }
  }, [config, refreshHealth])

  const costModels = useMemo(() => meta?.cost_models ?? { etf: 'ETF 费率' }, [meta])

  // 图表上正在展示的标的：优先用回测结果的标的，
  // 这样顶栏/图表不会出现「标的已改、图还是上一只」的不一致
  const chartSymbol = useMemo(() => {
    const code = result?.symbol ?? config.symbol
    const info = symbols.find((s) => s.symbol === code)
    return info ? `${info.symbol} ${info.name}` : code
  }, [result, config.symbol, symbols])

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* 顶栏 */}
      <header className="bg-background flex shrink-0 items-center justify-between border-b px-6 py-3">
        <div className="flex items-center gap-3">
          <div className="bg-primary/10 text-primary flex size-8 items-center justify-center rounded-lg">
            <CandlestickChart className="size-4" />
          </div>
          <h1 className="text-sm font-semibold">Hikyuu 回测</h1>
        </div>

        <div className="flex items-center gap-2">
          <EngineBadge
            state={engineState}
            detail={health?.detail}
            loadedSymbols={health?.loaded_symbols}
          />
          <ModeToggle />
        </div>
      </header>

      {/* 桌面端：左右两栏各自滚动；窄屏整页滚动 */}
      <main className="grid min-h-0 flex-1 grid-cols-1 gap-4 overflow-y-auto p-4 lg:grid-cols-[340px_1fr] lg:grid-rows-[minmax(0,1fr)] lg:overflow-hidden">
        {/* 左栏：参数 */}
        <Card className="lg:min-h-0 lg:overflow-y-auto">
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <CardTitle className="flex items-center gap-2 text-sm">
              <SlidersHorizontal className="text-muted-foreground size-4" />
              回测设置
            </CardTitle>
            <StrategyDrawer config={config} onChange={updateConfig} strategies={strategies} />
          </CardHeader>
          <CardContent>
            <StrategyForm
              config={config}
              onChange={updateConfig}
              symbols={symbols}
              costModels={costModels}
              onSubmit={run}
              running={running}
            />
          </CardContent>
        </Card>

        {/* 右栏：结果 */}
        <section className="flex min-h-0 flex-col gap-4 lg:overflow-y-auto">
          {error && (
            <div className="border-destructive/40 bg-destructive/10 text-destructive flex items-start gap-2 rounded-lg border px-4 py-3 text-sm">
              <TriangleAlert className="mt-0.5 size-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {!result && !error && (
            <div className="border-border text-muted-foreground flex flex-1 flex-col items-center justify-center gap-2 rounded-lg border border-dashed py-20 text-sm">
              <MousePointerClick className="size-5 opacity-60" />
              {running ? '回测运行中…' : '配置左侧参数后点击「运行回测」'}
            </div>
          )}

          {result && (
            <>
              <MetricsPanel
                metrics={result.metrics}
                initCash={result.init_cash}
                finalEquity={result.equity[result.equity.length - 1]?.value}
              />

              <Card className="gap-3 py-4">
                <CardHeader className="px-4">
                  <CardTitle className="flex min-w-0 flex-wrap items-center gap-2 text-sm">
                    <CandlestickChart className="text-muted-foreground size-4" />
                    K 线与指标
                    <Badge variant="secondary" className="font-normal">
                      {chartSymbol}
                    </Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent className="px-3">
                  <KlineChart
                    candles={result.candles}
                    overlays={overlays}
                    trades={result.trades}
                  />
                </CardContent>
              </Card>

              <Card className="gap-3 py-4">
                <CardHeader className="px-4">
                  <CardTitle className="flex min-w-0 flex-wrap items-center gap-2 text-sm">
                    <ChartLine className="text-muted-foreground size-4" />
                    资金曲线
                    <Badge variant="secondary" className="font-normal">
                      {chartSymbol}
                    </Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent className="px-3">
                  <EquityChart
                    equity={result.equity}
                    initCash={result.init_cash}
                  />
                </CardContent>
              </Card>

              <Card className="gap-3 py-4">
                <CardHeader className="px-4">
                  <CardTitle className="flex items-center gap-2 text-sm">
                    <Table2 className="text-muted-foreground size-4" />
                    成交明细
                    <Badge variant="secondary">{result.trades.length} 笔</Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                  <TradeTable trades={result.trades} />
                </CardContent>
              </Card>
            </>
          )}
        </section>
      </main>
    </div>
  )
}
