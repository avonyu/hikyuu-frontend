import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { CandlestickChart, Check, ChevronsUpDown } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Drawer,
  DrawerBody,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
  DrawerTrigger,
} from '@/components/ui/drawer'
import { Label } from '@/components/ui/label'
import { NumberInput } from '@/components/ui/number-input'
import { cn } from '@/lib/utils'
import type { StrategyConfig, StrategyInfo } from '../lib/types'

interface Props {
  config: StrategyConfig
  /** 传入要改的字段，内部与其它字段合并 */
  onChange: (patch: Partial<StrategyConfig>) => void
  strategies: StrategyInfo[]
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <Label>{label}</Label>
      {children}
    </div>
  )
}

export default function StrategyDrawer({ config, onChange, strategies }: Props) {
  const [open, setOpen] = useState(false)
  const [pickerOpen, setPickerOpen] = useState(false)
  const pickerRef = useRef<HTMLDivElement>(null)

  // 点击下拉区域之外或按 Esc 关闭；抽屉关闭时一并收起
  useEffect(() => {
    if (!pickerOpen) return
    const onPointerDown = (event: PointerEvent) => {
      if (!pickerRef.current?.contains(event.target as Node)) setPickerOpen(false)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setPickerOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [pickerOpen])

  // 加载失败的脚本不进入选项，只在选中时提示
  const usable = strategies.filter((s) => !s.error)
  const selected = strategies.find((s) => s.id === config.strategyId)
  const failed = selected?.error ? selected : strategies.find((s) => s.error)

  // 只保存用户手动改过的参数；未改动的参数跟随脚本里的 default
  const pickStrategy = (id: string) => onChange({ strategyId: id, strategyParams: {} })

  return (
    <Drawer
      direction="right"
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        // 抽屉关闭时一并收起下拉，避免下次打开时列表还开着
        if (!next) setPickerOpen(false)
      }}
    >
      <DrawerTrigger asChild>
        <Button type="button" variant="outline" size="sm" className="max-w-full">
          <CandlestickChart className="size-4" />
          <span className="truncate">{selected?.name ?? '选择策略'}</span>
        </Button>
      </DrawerTrigger>
      <DrawerContent>
        <DrawerHeader>
          <DrawerTitle>策略设置</DrawerTitle>
          <DrawerDescription>选择策略脚本并设置参数，回测时使用这里的设置</DrawerDescription>
        </DrawerHeader>

        <DrawerBody className="flex flex-col gap-4">
          <Field label="策略脚本">
            {/* 就地展开的下拉：触发器与列表用 shadcn Select 的样式。
                不用 Portal —— Radix 弹层在 vaul 抽屉里会因焦点管理与
                滑入动画（transform 干扰 Popper 测量）而错位或点不中 */}
            <div className="relative" ref={pickerRef}>
              <Button
                type="button"
                variant="outline"
                role="combobox"
                aria-expanded={pickerOpen}
                aria-controls="strategy-options"
                className="w-full justify-between font-normal"
                onClick={() => setPickerOpen((v) => !v)}
              >
                <span className="truncate">{selected?.name ?? '选择脚本'}</span>
                <ChevronsUpDown className="text-muted-foreground size-4 shrink-0" />
              </Button>

              {pickerOpen && (
                <div
                  id="strategy-options"
                  role="listbox"
                  aria-label="策略脚本"
                  className="bg-popover text-popover-foreground animate-in fade-in-0 zoom-in-95 absolute top-full left-0 z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-md border p-1 shadow-md"
                >
                  {usable.length === 0 && (
                    <p className="text-muted-foreground px-2 py-1.5 text-sm">
                      backend/strategies 下没有可用脚本
                    </p>
                  )}
                  {usable.map((s) => {
                    const active = s.id === config.strategyId
                    return (
                      <button
                        key={s.id}
                        type="button"
                        role="option"
                        aria-selected={active}
                        onClick={() => {
                          pickStrategy(s.id)
                          setPickerOpen(false)
                        }}
                        className={cn(
                          'hover:bg-accent hover:text-accent-foreground focus-visible:bg-accent focus-visible:text-accent-foreground flex w-full items-center justify-between gap-2 rounded-sm px-2 py-1.5 text-left text-sm outline-none',
                          active && 'bg-accent text-accent-foreground',
                        )}
                      >
                        <span className="truncate">{s.name}</span>
                        {active && <Check className="size-4 shrink-0" />}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          </Field>

          {selected?.description && (
            <p className="text-muted-foreground text-xs leading-relaxed">{selected.description}</p>
          )}
          {failed?.error && (
            <Badge variant="destructive" className="max-w-full truncate">
              加载失败：{failed.error}
            </Badge>
          )}
          {selected?.money_manager && (
            <p className="text-muted-foreground text-xs leading-relaxed">
              「{selected.name}」自带资金管理，回测设置中的资金管理对它不生效
            </p>
          )}

          {selected && selected.params.length > 0 && (
            <div className="grid grid-cols-2 gap-3">
              {selected.params.map((p) => {
                const current = config.strategyParams[p.name] ?? p.default
                const setParam = (value: number | string) =>
                  onChange({
                    strategyParams: { ...config.strategyParams, [p.name]: value },
                  })

                if (p.type === 'choice') {
                  return (
                    <Field key={p.name} label={p.label}>
                      <div className="flex flex-wrap gap-1.5">
                        {(p.choices ?? []).map((choice) => (
                          <Button
                            key={choice}
                            type="button"
                            size="sm"
                            variant={current === choice ? 'default' : 'secondary'}
                            className="flex-1 px-2 text-xs"
                            onClick={() => setParam(choice)}
                          >
                            {choice}
                          </Button>
                        ))}
                      </div>
                    </Field>
                  )
                }

                return (
                  <Field key={p.name} label={p.label}>
                    <NumberInput
                      min={p.min ?? undefined}
                      max={p.max ?? undefined}
                      decimals={p.integer ? 0 : 2}
                      step={p.integer ? 1 : 0.1}
                      value={typeof current === 'number' ? current : (p.default as number)}
                      onChange={(v) => setParam(v ?? Number(p.default))}
                    />
                  </Field>
                )
              })}
            </div>
          )}
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  )
}
