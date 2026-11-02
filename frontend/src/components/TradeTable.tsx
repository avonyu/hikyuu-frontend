import type { Trade } from '../lib/types'

interface Props {
  trades: Trade[]
}

/** 成交明细表。 */
export default function TradeTable({ trades }: Props) {
  if (trades.length === 0) {
    return (
      <div className="rounded border border-[var(--color-border)] bg-[var(--color-panel)] p-6 text-center text-xs text-[var(--color-fg-muted)]">
        本次回测没有产生成交
      </div>
    )
  }

  return (
    <div className="overflow-auto rounded border border-[var(--color-border)] bg-[var(--color-panel)]">
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-[var(--color-panel-2)]">
          <tr className="text-left text-[var(--color-fg-muted)]">
            <th className="px-3 py-2 font-medium">时间</th>
            <th className="px-3 py-2 font-medium">方向</th>
            <th className="px-3 py-2 text-right font-medium">价格</th>
            <th className="px-3 py-2 text-right font-medium">数量</th>
            <th className="px-3 py-2 text-right font-medium">佣金</th>
            <th className="px-3 py-2 text-right font-medium">印花税</th>
            <th className="px-3 py-2 text-right font-medium">现金余额</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t, i) => {
            const isBuy = t.business === 'BUY'
            return (
              <tr
                key={`${t.datetime}-${i}`}
                className="border-t border-[var(--color-border)] hover:bg-[var(--color-panel-2)]"
              >
                <td className="num px-3 py-1.5 text-[var(--color-fg-muted)]">
                  {t.datetime.slice(0, 16)}
                </td>
                <td className="px-3 py-1.5">
                  <span
                    className={
                      isBuy
                        ? 'text-[var(--color-up)]'
                        : 'text-[var(--color-down)]'
                    }
                  >
                    {isBuy ? '买入' : '卖出'}
                  </span>
                </td>                <td className="num px-3 py-1.5 text-right">{t.price.toFixed(3)}</td>
                <td className="num px-3 py-1.5 text-right">{t.number}</td>
                <td className="num px-3 py-1.5 text-right text-[var(--color-fg-muted)]">
                  {t.cost.commission.toFixed(2)}
                </td>
                <td className="num px-3 py-1.5 text-right text-[var(--color-fg-muted)]">
                  {t.cost.stamp_tax.toFixed(2)}
                </td>
                <td className="num px-3 py-1.5 text-right">
                  {t.cash.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
