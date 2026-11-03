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
  fetchStrategies,
  fetchSymbols,
  pollJob,
  submitBacktest,
} from './lib/api'
import { useHealth } from './lib/use-health'
import type { BacktestResult, Meta, StrategyInfo, SymbolInfo } from './lib/types'
import EquityChart from './components/EquityChart'
import KlineChart from './components/KlineChart'
import MetricsPanel from './components/MetricsPanel'
import StrategyForm, { type StrategyConfig } from './components/StrategyForm'
import TradeTable from './components/TradeTable'

const DEFAULT_CONFIG: StrategyConfig = {
  symbol: 'sh510300',
  start: '2023-01-01',
  end: '2024-12-31',
  init_cash: 300000,
  cost_model: 'etf',
  strategyMode: 'builtin',
  strategyId: '',
  strategyParams: {},
  signalType: 'cross',
  fast: 5,
  slow: 20,
  singleN: 20,
  moneyType: 'fixed_count',
  count: 1000,
  percent: 0.2,
  overlays: [
    { type: 'ma', n: 5 },
    { type: 'ma', n: 20 },
  ],
  stoploss: null,
  takeprofit: null,
  slippage: null,
}

export default function App() {
  const [config, setConfig] = useState<StrategyConfig>(DEFAULT_CONFIG)
  const [symbols, setSymbols] = useState<SymbolInfo[]>([])
  const [strategies, setStrategies] = useState<StrategyInfo[]>([])
  const [meta, setMeta] = useState<Meta | null>(null)
  const [result, setResult] = useState<BacktestResult | null>(null)
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
        if (s.length > 0) {
          const firstTradable = s.find((x) => x.kind !== 'INDEX')
          if (firstTradable) {
            setConfig((c) => ({ ...c, symbol: firstTradable.symbol }))
          }
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : '无法连接后端服务')
      }
    })()
  }, [])

  const run = useCallback(async () => {
    setRunning(true)
    setError(null)
    try {
      const { id } = await submitBacktest({
        symbol: config.symbol,
        start: config.start,
        end: config.end,
        init_cash: config.init_cash,
        cost_model: config.cost_model,
        signal: {
          type: config.signalType,
          fast: config.fast,
          slow: config.slow,
          n: config.singleN,
        },
        strategy:
          config.strategyMode === 'custom' && config.strategyId
            ? { id: config.strategyId, params: config.strategyParams }
            : null,
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

  const selectedSymbol = symbols.find((s) => s.symbol === config.symbol)

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* 顶栏 */}
      <header className="bg-background flex shrink-0 items-center justify-between border-b px-6 py-3">
        <div className="flex items-center gap-3">
          <div className="bg-primary/10 text-primary flex size-8 items-center justify-center rounded-lg">
            <CandlestickChart className="size-4" />
          </div>
          <div>
            <h1 className="text-sm font-semibold">Hikyuu 回测</h1>
            <p className="text-muted-foreground text-xs">
              {selectedSymbol
                ? `${selectedSymbol.symbol} ${selectedSymbol.name}`
                : config.symbol}
            </p>
          </div>
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
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <SlidersHorizontal className="text-muted-foreground size-4" />
              回测设置
            </CardTitle>
          </CardHeader>
          <CardContent>
            <StrategyForm
              config={config}
              onChange={setConfig}
              symbols={symbols}
              strategies={strategies}
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
              <MetricsPanel metrics={result.metrics} initCash={result.init_cash} />

              <Card className="gap-3 py-4">
                <CardHeader className="px-4">
                  <CardTitle className="flex items-center gap-2 text-sm">
                    <CandlestickChart className="text-muted-foreground size-4" />
                    K 线与指标
                  </CardTitle>
                </CardHeader>
                <CardContent className="px-3">
                  <KlineChart
                    candles={result.candles}
                    overlays={result.overlays}
                    trades={result.trades}
                  />
                </CardContent>
              </Card>

              <Card className="gap-3 py-4">
                <CardHeader className="px-4">
                  <CardTitle className="flex items-center gap-2 text-sm">
                    <ChartLine className="text-muted-foreground size-4" />
                    资金曲线
                  </CardTitle>
                </CardHeader>
                <CardContent className="px-3">
                  <EquityChart
                    candles={result.candles}
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
