import { Activity, ShieldAlert, TrendingDown, TrendingUp, Wallet } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import { Card, CardContent } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'

interface Props {
  metrics: Record<string, number>
  initCash: number
  /** 资金曲线末值；与图表一致，优先于 Hikyuu 的 Current Total Assets */
  finalEquity?: number
}

/** 需要突出显示的关键指标（后端返回的是 Hikyuu 的英文指标名） */
const KEY_METRICS: { key: string; label: string; format?: 'pct' | 'money' }[] = [
  { key: 'Total Net Profit of Closed Trades', label: '净盈利', format: 'money' },
  { key: 'Account Total Return %', label: '总收益率', format: 'pct' },
  { key: 'Max Drawdown %', label: '最大回撤', format: 'pct' },
  { key: 'Account CAGR %', label: '年化收益率', format: 'pct' },
  { key: 'Sharpe Ratio', label: '夏普比率' },
  { key: 'Win Rate %', label: '胜率', format: 'pct' },
  { key: 'Profit Factor', label: '盈亏比' },
  { key: 'Total Closed Trades', label: '总交易次数' },
]

function formatValue(value: number | undefined, format?: 'pct' | 'money') {
  if (value === undefined || value === null || Number.isNaN(value)) return '—'
  if (format === 'pct') return `${value.toFixed(2)}%`
  if (format === 'money') return value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
  if (Number.isInteger(value)) return value.toLocaleString('zh-CN')
  return value.toFixed(4)
}

function StatCard({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: LucideIcon
  label: string
  value: string
  tone?: 'up' | 'down'
}) {
  return (
    <Card className="gap-1 py-4">
      <CardContent className="px-4">
        <div className="text-muted-foreground flex items-center gap-1.5 text-xs">
          <Icon className="size-3.5" />
          {label}
        </div>
        <div
          className={cn(
            'num mt-2 text-2xl font-semibold',
            tone === 'up' && 'text-up',
            tone === 'down' && 'text-down',
          )}
        >
          {value}
        </div>
      </CardContent>
    </Card>
  )
}

/** 绩效指标面板：顶部关键指标 + 可展开的完整指标表。 */
export default function MetricsPanel({ metrics, initCash, finalEquity }: Props) {
  // 资金曲线末值 = 现金 + 持仓按末日收盘价盯市，与图表一致。
  // Hikyuu 的 Current Total Assets 在「末日仍有持仓」时会与它对不上，故优先用它。
  const equity =
    finalEquity ?? metrics['Current Total Assets'] ?? initCash
  const totalReturn =
    metrics['Account Total Return %'] ?? ((equity - initCash) / initCash) * 100
  const positive = totalReturn >= 0

  return (
    <div className="flex flex-col gap-4">
      {/* 关键指标卡片 */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard
          icon={Wallet}
          label="期末权益"
          value={equity.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}
        />
        <StatCard
          icon={positive ? TrendingUp : TrendingDown}
          label="总收益率"
          value={`${totalReturn.toFixed(2)}%`}
          tone={positive ? 'up' : 'down'}
        />
        <StatCard
          icon={ShieldAlert}
          label="最大回撤"
          value={formatValue(metrics['Max Drawdown %'], 'pct')}
        />
        <StatCard
          icon={Activity}
          label="夏普比率"
          value={formatValue(metrics['Sharpe Ratio'])}
        />
      </div>

      {/* 完整指标表 */}
      <details className="bg-card rounded-xl border">
        <summary className="text-muted-foreground hover:text-foreground cursor-pointer px-4 py-3 text-sm font-medium">
          全部 {Object.keys(metrics).length} 项指标
        </summary>
        <div className="max-h-80 overflow-auto border-t">
          <Table>
            <TableBody>
              {Object.entries(metrics).map(([name, value]) => {
                const known = KEY_METRICS.find((m) => m.key === name)
                return (
                  <TableRow key={name}>
                    <TableCell className="text-muted-foreground">
                      {known?.label ?? name}
                    </TableCell>
                    <TableCell className="num text-right">{formatValue(value)}</TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      </details>
    </div>
  )
}
