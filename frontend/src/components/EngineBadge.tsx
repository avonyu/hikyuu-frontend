import { Badge } from '@/components/ui/badge'
import type { EngineState } from '@/lib/types'
import { cn } from '@/lib/utils'

export interface EngineBadgeProps {
  /** 引擎状态；offline 表示后端不可达 */
  state: EngineState | 'offline'
  /** 后端附带的补充说明（悬浮提示） */
  detail?: string | null
  /** 已加载标的数 */
  loadedSymbols?: number
}

const STYLES: Record<
  EngineState | 'offline',
  { label: string; dot: string; pulse?: boolean }
> = {
  ready: { label: '引擎就绪', dot: 'bg-down' },
  loading: { label: '引擎加载中', dot: 'bg-warning animate-pulse' },
  idle: { label: '引擎待加载', dot: 'bg-muted-foreground' },
  error: { label: '引擎异常', dot: 'bg-destructive' },
  offline: { label: '服务未连接', dot: 'bg-destructive' },
}

/** 顶栏右上角的引擎状态指示标志。 */
export function EngineBadge({ state, detail, loadedSymbols }: EngineBadgeProps) {
  const style = STYLES[state] ?? STYLES.idle

  const tip =
    state === 'offline'
      ? '无法连接后端服务，请确认服务已启动'
      : [
          detail,
          loadedSymbols ? `已加载 ${loadedSymbols} 个标的` : null,
        ]
          .filter(Boolean)
          .join(' · ')

  return (
    <Badge
      variant="outline"
      className="gap-1.5"
      title={tip || undefined}
      aria-label={`引擎状态：${style.label}`}
    >
      <span
        aria-hidden="true"
        className={cn('size-1.5 shrink-0 rounded-full', style.dot, style.pulse)}
      />
      {style.label}
    </Badge>
  )
}
