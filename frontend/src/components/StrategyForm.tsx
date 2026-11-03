import type { ReactNode } from 'react'
import {
  Activity,
  CandlestickChart,
  Loader2,
  Percent,
  Play,
  ShieldAlert,
  Wallet,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { DatePicker } from '@/components/ui/date-picker'
import { Label } from '@/components/ui/label'
import { NumberInput } from '@/components/ui/number-input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { StrategyConfig, StrategyInfo, SymbolInfo } from '../lib/types'

export type { StrategyConfig }

interface Props {
  config: StrategyConfig
  /** 传入要改的字段，内部与其它字段合并 */
  onChange: (patch: Partial<StrategyConfig>) => void
  symbols: SymbolInfo[]
  strategies: StrategyInfo[]
  costModels: Record<string, string>
  onSubmit: () => void
  running: boolean
}

/** 可叠加的指标：MA/EMA/RSI 各三档周期，MACD 固定一档 */
const OVERLAY_OPTIONS = [
  { type: 'ma', n: 5, label: 'MA5' },
  { type: 'ma', n: 20, label: 'MA20' },
  { type: 'ma', n: 60, label: 'MA60' },
  { type: 'ema', n: 5, label: 'EMA5' },
  { type: 'ema', n: 20, label: 'EMA20' },
  { type: 'ema', n: 60, label: 'EMA60' },
  { type: 'rsi', n: 5, label: 'RSI5' },
  { type: 'rsi', n: 20, label: 'RSI20' },
  { type: 'rsi', n: 60, label: 'RSI60' },
  { type: 'macd', n: 12, label: 'MACD' },
]

/** 0.2 -> 20，顺手抹掉浮点噪声 */
const toPercentValue = (ratio: number) => Number((ratio * 100).toFixed(2))

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    // min-w-0：栅格/弹性子项默认 min-width:auto，长文本（如费率名）会把列撑破
    <div className="flex min-w-0 flex-col gap-2">
      <Label>{label}</Label>
      {children}
    </div>
  )
}

function SectionTitle({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <div className="text-muted-foreground flex items-center gap-2 text-xs font-medium">
      {icon}
      {children}
    </div>
  )
}

export default function StrategyForm({
  config,
  onChange,
  symbols,
  strategies,
  costModels,
  onSubmit,
  running,
}: Props) {
  const set = <K extends keyof StrategyConfig>(key: K, value: StrategyConfig[K]) =>
    onChange({ [key]: value } as Partial<StrategyConfig>)

  const tradable = symbols.filter((s) => s.kind !== 'INDEX')

  // 自定义脚本：加载失败的也列出来，但只在选中时提示
  const customStrategies = strategies.filter((s) => !s.error)
  const selectedStrategy = strategies.find((s) => s.id === config.strategyId)
  const failedStrategy = selectedStrategy?.error
    ? selectedStrategy
    : strategies.find((s) => s.error)

  const pickStrategy = (id: string) => {
    const found = strategies.find((s) => s.id === id)
    const params: Record<string, number> = {}
    found?.params.forEach((p) => {
      params[p.name] = Number(p.default)
    })
    onChange({
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
    const exists = config.overlays.some((o) => o.type === type && o.n === n)
    set(
      'overlays',
      exists
        ? config.overlays.filter((o) => !(o.type === type && o.n === n))
        : [...config.overlays, { type, n }],
    )
  }

  const isCross = config.strategyMode === 'builtin' && config.signalType === 'cross'
  const isSingle = config.strategyMode === 'builtin' && config.signalType === 'single'
  const isCustom = config.strategyMode === 'custom'

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        // 回测由按钮的 onClick 触发；这里只阻止回车键导致的原生提交
        e.preventDefault()
      }}
    >
      {/* 标的与区间 */}
      <Field label="标的">
        <Select value={config.symbol} onValueChange={(v) => set('symbol', v)}>
          <SelectTrigger className="w-full">
            <SelectValue placeholder="选择标的" />
          </SelectTrigger>
          <SelectContent>
            {tradable.map((s) => (
              <SelectItem key={s.symbol} value={s.symbol}>
                {s.symbol} {s.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>

      <div className="grid grid-cols-2 gap-2">
        <Field label="开始日期">
          <DatePicker value={config.start} onChange={(v) => set('start', v)} />
        </Field>
        <Field label="结束日期">
          <DatePicker value={config.end} onChange={(v) => set('end', v)} />
        </Field>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Field label="初始资金">
          <NumberInput
            min={1000}
            step={10000}
            value={config.init_cash}
            onChange={(v) => set('init_cash', v ?? 1000)}
          />
        </Field>
        <Field label="费率模型">
          <Select value={config.cost_model} onValueChange={(v) => set('cost_model', v)}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(costModels).map(([key, label]) => (
                <SelectItem key={key} value={key}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
      </div>

      {/* 策略 */}
      <div className="flex flex-col gap-2">
        <SectionTitle icon={<CandlestickChart className="size-3.5" />}>信号策略</SectionTitle>
        <div className="flex gap-1.5">
          <Button
            type="button"
            size="sm"
            variant={isCross ? 'default' : 'secondary'}
            className="flex-1"
            onClick={() =>
              onChange({ strategyMode: 'builtin', signalType: 'cross' })
            }
          >
            双均线交叉
          </Button>
          <Button
            type="button"
            size="sm"
            variant={isSingle ? 'default' : 'secondary'}
            className="flex-1"
            onClick={() =>
              onChange({ strategyMode: 'builtin', signalType: 'single' })
            }
          >
            单均线
          </Button>
          <Button
            type="button"
            size="sm"
            variant={isCustom ? 'default' : 'secondary'}
            className="flex-1"
            onClick={openCustom}
          >
            自定义脚本
          </Button>
        </div>
      </div>

      {isCustom ? (
        <div className="flex flex-col gap-2">
          <Field label="策略脚本">
            <Select value={config.strategyId} onValueChange={pickStrategy}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder="选择脚本" />
              </SelectTrigger>
              <SelectContent>
                {customStrategies.length === 0 && (
                  <SelectItem value="__none__" disabled>
                    backend/strategies 下没有可用脚本
                  </SelectItem>
                )}
                {customStrategies.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>

          {selectedStrategy?.description && (
            <p className="text-muted-foreground text-xs leading-relaxed">
              {selectedStrategy.description}
            </p>
          )}
          {failedStrategy?.error && (
            <Badge variant="destructive" className="max-w-full truncate">
              加载失败：{failedStrategy.error}
            </Badge>
          )}

          {selectedStrategy && selectedStrategy.params.length > 0 && (
            <div className="grid grid-cols-2 gap-2">
              {selectedStrategy.params.map((p) => (
                <Field key={p.name} label={p.label}>
                  <NumberInput
                    min={p.min ?? undefined}
                    max={p.max ?? undefined}
                    value={config.strategyParams[p.name] ?? p.default}
                    onChange={(v) =>
                      set('strategyParams', {
                        ...config.strategyParams,
                        [p.name]: v ?? Number(p.default),
                      })
                    }
                  />
                </Field>
              ))}
            </div>
          )}
        </div>
      ) : isCross ? (
        <div className="grid grid-cols-2 gap-2">
          <Field label="快线周期">
            <NumberInput min={1} value={config.fast} onChange={(v) => set('fast', v ?? 1)} />
          </Field>
          <Field label="慢线周期">
            <NumberInput min={1} value={config.slow} onChange={(v) => set('slow', v ?? 1)} />
          </Field>
        </div>
      ) : (
        <Field label="均线周期">
          <NumberInput min={1} value={config.singleN} onChange={(v) => set('singleN', v ?? 1)} />
        </Field>
      )}

      {/* 资金管理 */}
      <div className="flex flex-col gap-2">
        <SectionTitle icon={<Wallet className="size-3.5" />}>资金管理</SectionTitle>
        <div className="grid grid-cols-2 gap-2">
          <Select
            value={config.moneyType}
            onValueChange={(v) => set('moneyType', v as StrategyConfig['moneyType'])}
          >
            <SelectTrigger className="w-full min-w-0">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="fixed_count">固定股数</SelectItem>
              <SelectItem value="fixed_percent">固定比例</SelectItem>
            </SelectContent>
          </Select>
          {config.moneyType === 'fixed_count' ? (
            <NumberInput
              min={1}
              step={100}
              value={config.count}
              onChange={(v) => set('count', v ?? 1)}
            />
          ) : (
            <div className="relative min-w-0">
              <NumberInput
                min={1}
                max={100}
                step={1}
                decimals={2}
                className="pr-7"
                value={toPercentValue(config.percent)}
                onChange={(v) => set('percent', (v ?? 1) / 100)}
              />
              <Percent className="text-muted-foreground pointer-events-none absolute top-1/2 right-2 size-3.5 -translate-y-1/2" />
            </div>
          )}
        </div>
      </div>

      {/* 指标叠加 */}
      <div className="flex flex-col gap-2">
        <SectionTitle icon={<Activity className="size-3.5" />}>指标叠加</SectionTitle>
        <div className="grid grid-cols-2 gap-x-3 gap-y-2">
          {OVERLAY_OPTIONS.map((o) => {
            const id = `overlay-${o.type}-${o.n}`
            const checked = config.overlays.some((x) => x.type === o.type && x.n === o.n)
            return (
              <div key={id} className="flex items-center gap-2">
                <Checkbox
                  id={id}
                  checked={checked}
                  onCheckedChange={() => toggleOverlay(o.type, o.n)}
                />
                <Label htmlFor={id} className="text-sm font-normal">
                  {o.label}
                </Label>
              </div>
            )
          })}
        </div>
      </div>

      {/* 风控 */}
      <div className="flex flex-col gap-2">
        <SectionTitle icon={<ShieldAlert className="size-3.5" />}>风控</SectionTitle>
        <div className="grid grid-cols-3 gap-2">
          <Field label="止损 %">
            <NumberInput
              min={0}
              step={0.1}
              decimals={2}
              placeholder="无"
              value={config.stoploss === null ? null : toPercentValue(config.stoploss)}
              onChange={(v) => set('stoploss', v === null ? null : v / 100)}
            />
          </Field>
          <Field label="止盈 %">
            <NumberInput
              min={0}
              step={0.1}
              decimals={2}
              placeholder="无"
              value={config.takeprofit === null ? null : toPercentValue(config.takeprofit)}
              onChange={(v) => set('takeprofit', v === null ? null : v / 100)}
            />
          </Field>
          <Field label="滑点 %">
            <NumberInput
              min={0}
              step={0.1}
              decimals={2}
              placeholder="无"
              value={config.slippage === null ? null : toPercentValue(config.slippage)}
              onChange={(v) => set('slippage', v === null ? null : v / 100)}
            />
          </Field>
        </div>
      </div>

      <Button type="button" size="lg" onClick={onSubmit} disabled={running} className="mt-1 w-full">
        {running ? (
          <>
            <Loader2 className="size-4 animate-spin" />
            回测中…
          </>
        ) : (
          <>
            <Play className="size-4" />
            运行回测
          </>
        )}
      </Button>
    </form>
  )
}
