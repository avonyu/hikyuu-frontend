import { create } from 'zustand'
import { persist } from 'zustand/middleware'

import type { StrategyConfig } from './types'

/** 回测设置表单的默认值（也是持久化缺失字段时的兜底）。 */
export const DEFAULT_CONFIG: StrategyConfig = {
  symbol: 'sh510300',
  start: '2023-01-01',
  end: '2024-12-31',
  init_cash: 300000,
  cost_model: 'etf',
  strategyMode: 'builtin',
  strategyId: '',
  strategyParams: {},
  signalType: 'cross',
  fast: 5,
  slow: 20,
  singleN: 20,
  moneyType: 'fixed_count',
  count: 1000,
  percent: 0.2,
  overlays: [
    { type: 'ma', n: 5 },
    { type: 'ma', n: 20 },
  ],
  stoploss: null,
  takeprofit: null,
  slippage: null,
}

const STORAGE_KEY = 'hikyuu-backtest-config'

interface ConfigStore {
  config: StrategyConfig
  /** 合并式更新：只传要改的字段 */
  update: (patch: Partial<StrategyConfig>) => void
  /** 恢复默认设置 */
  reset: () => void
}

/**
 * 回测设置表单的全局状态，持久化到 localStorage。
 *
 * 只存表单配置，不存回测结果——结果每次都重新算。
 */
export const useConfigStore = create<ConfigStore>()(
  persist(
    (set) => ({
      config: DEFAULT_CONFIG,
      update: (patch) => set((s) => ({ config: { ...s.config, ...patch } })),
      reset: () => set({ config: DEFAULT_CONFIG }),
    }),
    {
      name: STORAGE_KEY,
      version: 1,
      // 重新挂载时用默认值补齐缺失字段，避免旧版本存的数据缺键
      merge: (persisted, current) => ({
        ...current,
        config: {
          ...DEFAULT_CONFIG,
          ...((persisted as { config?: Partial<StrategyConfig> } | undefined)?.config ?? {}),
        },
      }),
    },
  ),
)
