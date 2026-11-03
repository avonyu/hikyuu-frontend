import * as React from 'react'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

interface NumberInputProps
  extends Omit<React.ComponentProps<'input'>, 'value' | 'onChange' | 'type'> {
  /** null 表示空值（界面上显示为空，而不是 0） */
  value: number | null
  onChange: (value: number | null) => void
  min?: number
  max?: number
  /** 键盘上下键的步长，默认 1 */
  step?: number
  /** 保留的小数位，默认 0（整数） */
  decimals?: number
}

/**
 * 数字输入框（shadcn 没有官方 NumberInput，这里基于 Input 封装）。
 *
 * 与 <Input type="number"> 的区别：
 * - 用字符串草稿，允许清空、只输入负号，不会把 '' 变成 0；
 * - blur 时统一归一化：夹取到 [min, max]、round 到 decimals；
 * - 滚轮不响应（避免滚动页面时误改数值），上下键按 step 调整。
 */
export function NumberInput({
  value,
  onChange,
  min,
  max,
  step = 1,
  decimals = 0,
  className,
  onBlur,
  onKeyDown,
  ...props
}: NumberInputProps) {
  const [draft, setDraft] = React.useState(value === null ? '' : String(value))
  const focused = React.useRef(false)

  // 外部值变化时同步（回测结果回填、策略切换重置参数等）
  React.useEffect(() => {
    if (!focused.current) setDraft(value === null ? '' : String(value))
  }, [value])

  const clamp = (n: number) => {
    let out = n
    if (min !== undefined) out = Math.max(min, out)
    if (max !== undefined) out = Math.min(max, out)
    return Number(out.toFixed(decimals))
  }

  const commit = (raw: string) => {
    const text = raw.trim()
    if (text === '' || text === '-' || text === '.') {
      onChange(null)
      setDraft('')
      return
    }
    const parsed = Number(text)
    if (!Number.isFinite(parsed)) {
      onChange(null)
      setDraft('')
      return
    }
    const next = clamp(parsed)
    onChange(next)
    setDraft(String(next))
  }

  return (
    <Input
      {...props}
      type="text"
      inputMode={decimals > 0 ? 'decimal' : 'numeric'}
      value={draft}
      className={cn('num', className)}
      onFocus={(e) => {
        focused.current = true
        e.currentTarget.select()
      }}
      onWheel={(e) => e.currentTarget.blur()}
      onChange={(e) => {
        const raw = e.target.value
        // 只允许数字、一个小数点和开头的负号
        if (raw !== '' && !/^-?\d*\.?\d*$/.test(raw)) return
        setDraft(raw)
      }}
      onBlur={(e) => {
        focused.current = false
        commit(e.target.value)
        onBlur?.(e)
      }}
      onKeyDown={(e) => {
        if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
          e.preventDefault()
          const base = draft === '' ? (min ?? 0) : Number(draft)
          if (!Number.isFinite(base)) return
          const next = clamp(base + (e.key === 'ArrowUp' ? step : -step))
          onChange(next)
          setDraft(String(next))
          return
        }
        onKeyDown?.(e)
      }}
    />
  )
}
