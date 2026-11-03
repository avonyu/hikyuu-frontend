import { useMemo, useState } from 'react'
import { format, parseISO } from 'date-fns'
import { zhCN } from 'date-fns/locale'
import { CalendarDays } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Calendar } from '@/components/ui/calendar'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'

/** 年份下拉的默认上限：今年 + 1（模块级求值，避免在 render 里调 Date.now） */
const DEFAULT_TO_YEAR = new Date().getFullYear() + 1

interface DatePickerProps {
  /** YYYY-MM-DD */
  value: string
  onChange: (value: string) => void
  className?: string
  placeholder?: string
  /** 年份下拉的起止（含） */
  fromYear?: number
  toYear?: number
}

/** 日期选择器：按钮 + 下拉日历，值统一为 YYYY-MM-DD 字符串。 */
export function DatePicker({
  value,
  onChange,
  className,
  placeholder = '选择日期',
  fromYear = 1990,
  toYear = DEFAULT_TO_YEAR,
}: DatePickerProps) {
  const [open, setOpen] = useState(false)
  const date = value ? parseISO(value) : undefined

  const months = useMemo(
    () => ({ startMonth: new Date(fromYear, 0), endMonth: new Date(toYear, 11) }),
    [fromYear, toYear],
  )

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          className={cn(
            'w-full justify-start gap-2 font-normal',
            !date && 'text-muted-foreground',
            className,
          )}
        >
          <CalendarDays className="size-3.5 text-muted-foreground" />
          {date ? format(date, 'yyyy-MM-dd') : placeholder}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-2" align="start">
        <Calendar
          mode="single"
          locale={zhCN}
          captionLayout="dropdown"
          startMonth={months.startMonth}
          endMonth={months.endMonth}
          selected={date}
          defaultMonth={date}
          onSelect={(next) => {
            if (next) {
              onChange(format(next, 'yyyy-MM-dd'))
              setOpen(false)
            }
          }}
        />
      </PopoverContent>
    </Popover>
  )
}
