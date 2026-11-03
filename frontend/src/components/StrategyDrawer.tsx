import { useState } from 'react'
import type { ReactNode } from 'react'
import { CandlestickChart } from 'lucide-react'

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

  // 加载失败的脚本不进入选项，只在选中时提示
  const usable = strategies.filter((s) => !s.error)
  const selected = strategies.find((s) => s.id === config.strategyId)
  const failed = selected?.error ? selected : strategies.find((s) => s.error)

  // 只保存用户手动改过的参数；未改动的参数跟随脚本里的 default
  const pickStrategy = (id: string) => onChange({ strategyId: id, strategyParams: {} })

  return (
    <Drawer direction="right" open={open} onOpenChange={setOpen}>
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
            {/* 原生下拉框：Radix Select 在抽屉里的选项点不中，原生 select 不受弹层影响 */}
            <select
              value={config.strategyId}
              onChange={(e) => pickStrategy(e.target.value)}
              className="border-input dark:bg-input/30 focus-visible:border-ring focus-visible:ring-ring/50 h-9 w-full cursor-pointer rounded-md border bg-transparent px-3 py-1 text-sm shadow-xs outline-none focus-visible:ring-[3px]"
            >
              {usable.length === 0 && <option value="">backend/strategies 下没有可用脚本</option>}
              {usable.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
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
              {selected.params.map((p) => (
                <Field key={p.name} label={p.label}>
                  <NumberInput
                    min={p.min ?? undefined}
                    max={p.max ?? undefined}
                    decimals={p.integer ? 0 : 2}
                    step={p.integer ? 1 : 0.1}
                    value={config.strategyParams[p.name] ?? p.default}
                    onChange={(v) =>
                      onChange({
                        strategyParams: {
                          ...config.strategyParams,
                          [p.name]: v ?? Number(p.default),
                        },
                      })
                    }
                  />
                </Field>
              ))}
            </div>
          )}
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  )
}
