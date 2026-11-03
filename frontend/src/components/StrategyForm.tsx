import type { StrategyInfo, SymbolInfo } from '../lib/types'

export interface StrategyConfig {
  symbol: string
  start: string
  end: string
  init_cash: number
  cost_model: string
  strategyMode: 'builtin' | 'custom'
  strategyId: string
  strategyParams: Record<string, number>
  signalType: 'cross' | 'single'
  fast: number
  slow: number
  singleN: number
  moneyType: 'fixed_count' | 'fixed_percent'
  count: number
  percent: number
  overlays: { type: string; n: number }[]
  stoploss: number | null
  takeprofit: number | null
  slippage: number | null
}

interface Props {
  config: StrategyConfig
  onChange: (config: StrategyConfig) => void
  symbols: SymbolInfo[]
  strategies: StrategyInfo[]
  costModels: Record<string, string>
  onSubmit: () => void
  running: boolean
}

const OVERLAY_TYPES = [
  { value: 'ma', label: 'MA' },
  { value: 'ema', label: 'EMA' },
  { value: 'rsi', label: 'RSI' },
  { value: 'macd', label: 'MACD' },
]

const inputCls =
  'w-full rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1.5 text-xs text-[var(--color-fg)] outline-none focus:border-[var(--color-accent)]'
const labelCls = 'mb-1 block text-[11px] text-[var(--color-fg-muted)]'

export default function StrategyForm({
  config,
  onChange,
  symbols,
  strategies,
  costModels,
  onSubmit,
  running,
}: Props) {
  const set = <K extends keyof StrategyConfig>(
    key: K,
    value: StrategyConfig[K],
  ) => onChange({ ...config, [key]: value })

  const tradable = symbols.filter((s) => s.kind !== 'INDEX')

  // 自定义脚本：加载失败的也列出来，但只在选中时提示
  const customStrategies = strategies.filter((s) => !s.error)
  const selectedStrategy = strategies.find((s) => s.id === config.strategyId)
  const failedStrategy =
    selectedStrategy?.error ? selectedStrategy : strategies.find((s) => s.error)

  const pickStrategy = (id: string) => {
    const found = strategies.find((s) => s.id === id)
    const params: Record<string, number> = {}
    found?.params.forEach((p) => {
      params[p.name] = Number(p.default)
    })
    onChange({
      ...config,
      strategyMode: 'custom',
      strategyId: id,
      strategyParams: params,
    })
  }

  const openCustom = () => {
    if (config.strategyId) {
      set('strategyMode', 'custom')
    } else if (customStrategies.length > 0) {
      pickStrategy(customStrategies[0].id)
    } else {
      set('strategyMode', 'custom')
    }
  }

  const toggleOverlay = (type: string, n: number) => {
    const exists = config.overlays.some(
      (o) => o.type === type && o.n === n,
    )
    const overlays = exists
      ? config.overlays.filter((o) => !(o.type === type && o.n === n))
      : [...config.overlays, { type, n }]
    set('overlays', overlays)
  }

  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        // 回测由按钮的 onClick 触发；这里只阻止回车键导致的原生提交
        e.preventDefault()
      }}
    >
      {/* 标的 */}
      <div>
        <label className={labelCls}>标的</label>
        <select
          className={inputCls}
          value={config.symbol}
          onChange={(e) => set('symbol', e.target.value)}
        >
          {tradable.length === 0 && <option value={config.symbol}>{config.symbol}</option>}
          {tradable.map((s) => (
            <option key={s.symbol} value={s.symbol}>
              {s.symbol} {s.name}
            </option>
          ))}
        </select>
      </div>

      {/* 区间与资金 */}
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className={labelCls}>开始日期</label>
          <input
            type="date"
            className={inputCls}
            value={config.start}
            onChange={(e) => set('start', e.target.value)}
          />
        </div>
        <div>
          <label className={labelCls}>结束日期</label>
          <input
            type="date"
            className={inputCls}
            value={config.end}
            onChange={(e) => set('end', e.target.value)}
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className={labelCls}>初始资金</label>
          <input
            type="number"
            className={inputCls}
            value={config.init_cash}
            min={1000}
            step={10000}
            onChange={(e) => set('init_cash', Number(e.target.value))}
          />
        </div>
        <div>
          <label className={labelCls}>费率模型</label>
          <select
            className={inputCls}
            value={config.cost_model}
            onChange={(e) => set('cost_model', e.target.value)}
          >
            {Object.entries(costModels).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* 策略来源 */}
      <div>
        <label className={labelCls}>信号策略</label>
        <div className="flex gap-1.5">
          <button
            type="button"
            onClick={() =>
              onChange({ ...config, strategyMode: 'builtin', signalType: 'cross' })
            }
            className={`flex-1 rounded px-2 py-1.5 text-xs ${
              config.strategyMode === 'builtin' && config.signalType === 'cross'
                ? 'bg-[var(--color-accent)] text-[var(--color-bg)]'
                : 'bg-[var(--color-panel-2)] text-[var(--color-fg-muted)]'
            }`}
          >
            双均线交叉
          </button>
          <button
            type="button"
            onClick={() =>
              onChange({ ...config, strategyMode: 'builtin', signalType: 'single' })
            }
            className={`flex-1 rounded px-2 py-1.5 text-xs ${
              config.strategyMode === 'builtin' && config.signalType === 'single'
                ? 'bg-[var(--color-accent)] text-[var(--color-bg)]'
                : 'bg-[var(--color-panel-2)] text-[var(--color-fg-muted)]'
            }`}
          >
            单均线
          </button>
          <button
            type="button"
            onClick={openCustom}
            className={`flex-1 rounded px-2 py-1.5 text-xs ${
              config.strategyMode === 'custom'
                ? 'bg-[var(--color-accent)] text-[var(--color-bg)]'
                : 'bg-[var(--color-panel-2)] text-[var(--color-fg-muted)]'
            }`}
          >
            自定义脚本
          </button>
        </div>
      </div>

      {config.strategyMode === 'custom' ? (
        <div className="flex flex-col gap-2">
          <div>
            <label className={labelCls}>策略脚本</label>
            <select
              className={inputCls}
              value={config.strategyId}
              onChange={(e) => pickStrategy(e.target.value)}
            >
              {customStrategies.length === 0 && (
                <option value="">backend/strategies 下没有可用脚本</option>
              )}
              {customStrategies.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
            {selectedStrategy?.description && (
              <p className="mt-1 text-[11px] leading-relaxed text-[var(--color-fg-muted)]">
                {selectedStrategy.description}
              </p>
            )}
            {failedStrategy?.error && (
              <p className="mt-1 text-[11px] text-[var(--color-up)]">
                加载失败：{failedStrategy.error}
              </p>
            )}
          </div>

          {selectedStrategy && selectedStrategy.params.length > 0 && (
            <div className="grid grid-cols-2 gap-2">
              {selectedStrategy.params.map((p) => (
                <div key={p.name}>
                  <label className={labelCls}>{p.label}</label>
                  <input
                    type="number"
                    className={inputCls}
                    value={config.strategyParams[p.name] ?? p.default}
                    min={p.min ?? undefined}
                    max={p.max ?? undefined}
                    onChange={(e) =>
                      set('strategyParams', {
                        ...config.strategyParams,
                        [p.name]: Number(e.target.value),
                      })
                    }
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      ) : config.signalType === 'cross' ? (
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className={labelCls}>快线周期</label>
            <input
              type="number"
              className={inputCls}
              value={config.fast}
              min={1}
              onChange={(e) => set('fast', Number(e.target.value))}
            />
          </div>
          <div>
            <label className={labelCls}>慢线周期</label>
            <input
              type="number"
              className={inputCls}
              value={config.slow}
              min={1}
              onChange={(e) => set('slow', Number(e.target.value))}
            />
          </div>
        </div>
      ) : (
        <div>
          <label className={labelCls}>均线周期</label>
          <input
            type="number"
            className={inputCls}
            value={config.singleN}
            min={1}
            onChange={(e) => set('singleN', Number(e.target.value))}
          />
        </div>
      )}

      {/* 资金管理 */}
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className={labelCls}>资金管理</label>
          <select
            className={inputCls}
            value={config.moneyType}
            onChange={(e) =>
              set('moneyType', e.target.value as StrategyConfig['moneyType'])
            }
          >
            <option value="fixed_count">固定股数</option>
            <option value="fixed_percent">固定比例</option>
          </select>
        </div>
        {config.moneyType === 'fixed_count' ? (
          <div>
            <label className={labelCls}>每次股数</label>
            <input
              type="number"
              className={inputCls}
              value={config.count}
              min={1}
              step={100}
              onChange={(e) => set('count', Number(e.target.value))}
            />
          </div>
        ) : (
          <div>
            <label className={labelCls}>每次比例 (%)</label>
            <input
              type="number"
              className={inputCls}
              value={config.percent * 100}
              min={1}
              max={100}
              onChange={(e) => set('percent', Number(e.target.value) / 100)}
            />
          </div>
        )}
      </div>

      {/* 指标叠加 */}
      <div>
        <label className={labelCls}>指标叠加</label>
        <div className="flex flex-wrap gap-1.5">
          {OVERLAY_TYPES.flatMap((t) =>
            t.value === 'macd'
              ? [
                  <button
                    key="macd"
                    type="button"
                    onClick={() => toggleOverlay('macd', 12)}
                    className={`rounded px-2 py-1 text-[11px] ${
                      config.overlays.some((o) => o.type === 'macd')
                        ? 'bg-[var(--color-accent)] text-[var(--color-bg)]'
                        : 'bg-[var(--color-panel-2)] text-[var(--color-fg-muted)]'
                    }`}
                  >
                    MACD
                  </button>,
                ]
              : [5, 20, 60].map((n) => (
                  <button
                    key={`${t.value}${n}`}
                    type="button"
                    onClick={() => toggleOverlay(t.value, n)}
                    className={`rounded px-2 py-1 text-[11px] ${
                      config.overlays.some((o) => o.type === t.value && o.n === n)
                        ? 'bg-[var(--color-accent)] text-[var(--color-bg)]'
                        : 'bg-[var(--color-panel-2)] text-[var(--color-fg-muted)]'
                    }`}
                  >
                    {t.label}
                    {n}
                  </button>
                )),
          )}
        </div>
      </div>

      {/* 风控 */}
      <div className="grid grid-cols-3 gap-2">
        <div>
          <label className={labelCls}>止损 %</label>
          <input
            type="number"
            className={inputCls}
            value={config.stoploss ?? ''}
            min={0}
            step={1}
            placeholder="无"
            onChange={(e) =>
              set('stoploss', e.target.value ? Number(e.target.value) / 100 : null)
            }
          />
        </div>
        <div>
          <label className={labelCls}>止盈 %</label>
          <input
            type="number"
            className={inputCls}
            value={config.takeprofit ?? ''}
            min={0}
            step={1}
            placeholder="无"
            onChange={(e) =>
              set('takeprofit', e.target.value ? Number(e.target.value) / 100 : null)
            }
          />
        </div>
        <div>
          <label className={labelCls}>滑点 %</label>
          <input
            type="number"
            className={inputCls}
            value={config.slippage ?? ''}
            min={0}
            step={0.1}
            placeholder="无"
            onChange={(e) =>
              set('slippage', e.target.value ? Number(e.target.value) / 100 : null)
            }
          />
        </div>
      </div>

      <button
        type="button"
        onClick={onSubmit}
        disabled={running}
        className="rounded bg-[var(--color-accent)] px-3 py-2 text-xs font-medium text-[var(--color-bg)] transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {running ? '回测中…' : '运行回测'}
      </button>
    </form>
  )
}
