import { ArrowDownRight, ArrowUpRight, Inbox } from 'lucide-react'

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { Trade } from '../lib/types'

interface Props {
  trades: Trade[]
}

/** 成交明细表。 */
export default function TradeTable({ trades }: Props) {
  if (trades.length === 0) {
    return (
      <div className="text-muted-foreground flex flex-col items-center gap-2 border-t px-6 py-10 text-sm">
        <Inbox className="size-5 opacity-60" />
        本次回测没有产生成交
      </div>
    )
  }

  return (
    <Table className="border-t">
      <TableHeader className="bg-card sticky top-0">
        <TableRow className="hover:bg-transparent">
          <TableHead>时间</TableHead>
          <TableHead>方向</TableHead>
          <TableHead className="text-right">价格</TableHead>
          <TableHead className="text-right">数量</TableHead>
          <TableHead className="text-right">佣金</TableHead>
          <TableHead className="text-right">印花税</TableHead>
          <TableHead className="text-right">现金余额</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {trades.map((t, i) => {
          const isBuy = t.business === 'BUY'
          return (
            <TableRow key={`${t.datetime}-${i}`}>
              <TableCell className="num text-muted-foreground">
                {t.datetime.slice(0, 16)}
              </TableCell>
              <TableCell>
                <span
                  className={`flex items-center gap-0.5 ${isBuy ? 'text-up' : 'text-down'}`}
                >
                  {isBuy ? (
                    <ArrowUpRight className="size-3.5" />
                  ) : (
                    <ArrowDownRight className="size-3.5" />
                  )}
                  {isBuy ? '买入' : '卖出'}
                </span>
              </TableCell>
              <TableCell className="num text-right">{t.price.toFixed(3)}</TableCell>
              <TableCell className="num text-right">{t.number}</TableCell>
              <TableCell className="num text-right text-muted-foreground">
                {t.cost.commission.toFixed(2)}
              </TableCell>
              <TableCell className="num text-right text-muted-foreground">
                {t.cost.stamp_tax.toFixed(2)}
              </TableCell>
              <TableCell className="num text-right">
                {t.cash.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}
