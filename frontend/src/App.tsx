import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  fetchHealth,
  fetchMeta,
  fetchSymbols,
  pollJob,
  submitBacktest,
} from './lib/api'
import type { BacktestResult, Health, Meta, SymbolInfo } from './lib/types'
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
  const [meta, setMeta] = useState<Meta | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void (async () => {
      try {
        const [s, m, h] = await Promise.all([
          fetchSymbols(),
          fetchMeta(),
          fetchHealth(),
        ])
        setSymbols(s)
        setMeta(m)
        setHealth(h)
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
    }
  }, [config])

  const costModels = useMemo(
    () => meta?.cost_models ?? { etf: 'ETF 费率' },
    [meta],
  )

  const selectedSymbol = symbols.find((s) => s.symbol === config.symbol)

  return (
    <div className="flex min-h-full flex-col">
      {/* 顶栏 */}
      <header className="flex items-center justify-between border-b border-[var(--color-border)] px-5 py-3">
        <div>
          <h1 className="text-sm font-semibold">Hikyuu 回测</h1>
          <p className="mt-0.5 text-[11px] text-[var(--color-fg-muted)]">
            {selectedSymbol
              ? `${selectedSymbol.symbol} ${selectedSymbol.name}`
              : config.symbol}
          </p>
        </div>
        <div className="flex items-center gap-3 text-[11px] text-[var(--color-fg-muted)]">
          {health && (
            <>
              <span>
                标的 <span className="num">{health.available_symbols}</span>
              </span>
              <span
                className={
                  health.engine_ready ? 'text-[var(--color-down)]' : 'text-[var(--color-warn)]'
                }
              >
                引擎 {health.engine_ready ? '就绪' : '待加载'}
              </span>
            </>
          )}
        </div>
      </header>

      <main className="grid flex-1 grid-cols-1 gap-4 p-4 lg:grid-cols-[280px_1fr]">
        {/* 左栏：参数 */}
        <aside className="rounded border border-[var(--color-border)] bg-[var(--color-panel)] p-4">
          <h2 className="mb-3 text-xs font-semibold text-[var(--color-fg-muted)]">
            回测设置
          </h2>
          <StrategyForm
            config={config}
            onChange={setConfig}
            symbols={symbols}
            costModels={costModels}
            onSubmit={run}
            running={running}
          />
        </aside>

        {/* 右栏：结果 */}
        <section className="flex flex-col gap-4">
          {error && (
            <div className="rounded border border-[var(--color-up)] bg-[var(--color-up)]/10 px-3 py-2 text-xs text-[var(--color-up)]">
              {error}
            </div>
          )}

          {!result && !error && (
            <div className="flex flex-1 items-center justify-center rounded border border-dashed border-[var(--color-border)] py-20 text-xs text-[var(--color-fg-muted)]">
              {running ? '回测运行中…' : '配置左侧参数后点击「运行回测」'}
            </div>
          )}

          {result && (
            <>
              <div className="rounded border border-[var(--color-border)] bg-[var(--color-panel)] p-4">
                <MetricsPanel metrics={result.metrics} initCash={result.init_cash} />
              </div>

              <div className="rounded border border-[var(--color-border)] bg-[var(--color-panel)] p-3">
                <h3 className="mb-2 text-[11px] font-medium text-[var(--color-fg-muted)]">
                  K 线与指标
                </h3>
                <KlineChart
                  candles={result.candles}
                  overlays={result.overlays}
                  trades={result.trades}
                />
              </div>

              <div className="rounded border border-[var(--color-border)] bg-[var(--color-panel)] p-3">
                <h3 className="mb-2 text-[11px] font-medium text-[var(--color-fg-muted)]">
                  资金曲线
                </h3>
                <EquityChart
                  candles={result.candles}
                  equity={result.equity}
                  initCash={result.init_cash}
                />
              </div>

              <div>
                <h3 className="mb-2 text-[11px] font-medium text-[var(--color-fg-muted)]">
                  成交明细（{result.trades.length} 笔）
                </h3>
                <TradeTable trades={result.trades} />
              </div>
            </>
          )}
        </section>
      </main>
    </div>
  )
}
