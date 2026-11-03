import type { ReactNode } from 'react'
import {
  Activity,
  Loader2,
  Percent,
  Play,
  ShieldAlert,
  Wallet,
} from 'lucide-react'

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
import type { StrategyConfig, SymbolInfo } from '../lib/types'

export type { StrategyConfig }

interface Props {
  config: StrategyConfig
  /** 传入要改的字段，内部与其它字段合并 */
  onChange: (patch: Partial<StrategyConfig>) => void
  symbols: SymbolInfo[]
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
  costModels,
  onSubmit,
  running,
}: Props) {
  const set = <K extends keyof StrategyConfig>(key: K, value: StrategyConfig[K]) =>
    onChange({ [key]: value } as Partial<StrategyConfig>)

  const tradable = symbols.filter((s) => s.kind !== 'INDEX')

  const toggleOverlay = (type: string, n: number) => {
    const exists = config.overlays.some((o) => o.type === type && o.n === n)
    set(
      'overlays',
      exists
        ? config.overlays.filter((o) => !(o.type === type && o.n === n))
        : [...config.overlays, { type, n }],
    )
  }

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
              max={100}
              step={0.1}
              decimals={2}
              placeholder="无"
              value={config.stoploss === null ? null : toPercentValue(config.stoploss)}
              // 填 0 等同于不设止损：后端要求必须大于 0，传 0 会直接报错
              onChange={(v) => set('stoploss', v === null || v <= 0 ? null : v / 100)}
            />
          </Field>
          <Field label="止盈 %">
            <NumberInput
              min={0}
              step={0.1}
              decimals={2}
              placeholder="无"
              value={config.takeprofit === null ? null : toPercentValue(config.takeprofit)}
              onChange={(v) => set('takeprofit', v === null || v <= 0 ? null : v / 100)}
            />
          </Field>
          <Field label="滑点 %">
            <NumberInput
              min={0}
              max={100}
              step={0.1}
              decimals={2}
              placeholder="无"
              value={config.slippage === null ? null : toPercentValue(config.slippage)}
              onChange={(v) => set('slippage', v === null || v <= 0 ? null : v / 100)}
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
