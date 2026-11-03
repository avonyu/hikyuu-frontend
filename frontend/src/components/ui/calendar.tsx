import type { ComponentProps } from 'react'
import { DayPicker } from 'react-day-picker'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'

/** 基于 react-day-picker 的日历，样式遵循 shadcn 的 calendar 约定。 */
export function Calendar({
  className,
  classNames,
  showOutsideDays = true,
  ...props
}: ComponentProps<typeof DayPicker>) {
  return (
    <DayPicker
      showOutsideDays={showOutsideDays}
      className={cn('p-3', className)}
      classNames={{
        months: 'relative flex flex-col gap-4 md:flex-row',
        month: 'flex w-full flex-col gap-4',
        nav: 'absolute inset-x-0 top-0 flex w-full items-center justify-between gap-1',
        button_previous:
          'inline-flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground',
        button_next:
          'inline-flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground',
        chevron: 'size-4',
        month_caption: 'flex h-7 w-full items-center justify-center',
        caption_label: 'text-sm font-medium',
        dropdowns: 'flex items-center gap-1',
        dropdown_root:
          'relative inline-flex h-7 items-center rounded-md border border-input px-2 text-sm',
        dropdown: 'absolute inset-0 cursor-pointer opacity-0',
        month_grid: 'w-full border-collapse',
        weekdays: 'flex',
        weekday: 'w-8 rounded-md text-[0.8rem] font-normal text-muted-foreground',
        week: 'mt-2 flex w-full',
        day: 'relative size-8 p-0 text-center text-sm',
        day_button:
          'size-8 rounded-md transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none',
        selected: 'rounded-md bg-primary text-primary-foreground',
        today: 'font-semibold text-primary',
        outside: 'text-muted-foreground/50',
        disabled: 'opacity-50',
        hidden: 'invisible',
        ...classNames,
      }}
      components={{
        Chevron: ({ orientation }) =>
          orientation === 'left' ? (
            <ChevronLeft className="size-4" />
          ) : (
            <ChevronRight className="size-4" />
          ),
      }}
      {...props}
    />
  )
}
