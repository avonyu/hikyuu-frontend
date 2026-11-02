interface Props {
  metrics: Record<string, number>
  initCash: number
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

/** 绩效指标面板：顶部关键指标 + 可展开的完整指标表。 */
export default function MetricsPanel({ metrics, initCash }: Props) {
  const finalEquity = metrics['Current Total Assets'] ?? initCash
  const totalReturn =
    metrics['Account Total Return %'] ??
    ((finalEquity - initCash) / initCash) * 100
  const positive = totalReturn >= 0

  return (
    <div className="flex flex-col gap-3">
      {/* 关键指标卡片 */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <div className="rounded border border-[var(--color-border)] bg-[var(--color-panel)] p-3">
          <div className="text-[11px] text-[var(--color-fg-muted)]">期末权益</div>
          <div className="num mt-1 text-lg font-semibold">
            {finalEquity.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}
          </div>
        </div>
        <div className="rounded border border-[var(--color-border)] bg-[var(--color-panel)] p-3">
          <div className="text-[11px] text-[var(--color-fg-muted)]">总收益率</div>
          <div
            className={`num mt-1 text-lg font-semibold ${
              positive ? 'text-[var(--color-up)]' : 'text-[var(--color-down)]'
            }`}
          >
            {totalReturn.toFixed(2)}%
          </div>
        </div>
        <div className="rounded border border-[var(--color-border)] bg-[var(--color-panel)] p-3">
          <div className="text-[11px] text-[var(--color-fg-muted)]">最大回撤</div>
          <div className="num mt-1 text-lg font-semibold text-[var(--color-warn)]">
            {formatValue(metrics['Max Drawdown %'], 'pct')}
          </div>
        </div>
        <div className="rounded border border-[var(--color-border)] bg-[var(--color-panel)] p-3">
          <div className="text-[11px] text-[var(--color-fg-muted)]">夏普比率</div>
          <div className="num mt-1 text-lg font-semibold">
            {formatValue(metrics['Sharpe Ratio'])}
          </div>
        </div>
      </div>

      {/* 完整指标表 */}
      <details className="rounded border border-[var(--color-border)] bg-[var(--color-panel)]">
        <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-[var(--color-fg-muted)] hover:text-[var(--color-fg)]">
          全部 {Object.keys(metrics).length} 项指标
        </summary>
        <div className="max-h-80 overflow-auto border-t border-[var(--color-border)]">
          <table className="w-full text-xs">
            <tbody>
              {Object.entries(metrics).map(([name, value]) => {
                const known = KEY_METRICS.find((m) => m.key === name)
                return (
                  <tr key={name} className="border-b border-[var(--color-border)] last:border-0">
                    <td className="px-3 py-1.5 text-[var(--color-fg-muted)]">
                      {known?.label ?? name}
                    </td>
                    <td className="num px-3 py-1.5 text-right">{formatValue(value)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  )
}
