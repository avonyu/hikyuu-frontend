/** 与后端 API 对应的类型定义。 */

export interface Candle {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface TradeCost {
  commission: number
  stamp_tax: number
  transfer_fee: number
  others: number
}

export interface Trade {
  datetime: string
  code: string
  name: string
  business: string
  price: number
  plan_price: number
  number: number
  cash: number
  cost: TradeCost
}

export interface BacktestResult {
  symbol: string
  start: string
  end: string
  init_cash: number
  cost_model: string
  metrics: Record<string, number>
  candles: Candle[]
  equity: number[]
  trades: Trade[]
  overlays: Record<string, number[]>
}

export interface Job {
  id: string
  status: 'queued' | 'running' | 'done' | 'error'
  created_at: number
  started_at?: number
  finished_at?: number
  error?: string
  traceback?: string
  result?: BacktestResult
  request?: Record<string, unknown>
}

export interface SymbolInfo {
  symbol: string
  market: string
  code: string
  name: string
  kind: string
  last_date: string | null
}

export interface Health {
  status: string
  engine_ready: boolean
  loaded_symbols: number
  available_symbols: number
  cost_models: Record<string, string>
  detail: string | null
}

export interface Meta {
  cost_models: Record<string, string>
  default_symbol: string
  default_overlays: { type: string; n: number }[]
}

/** 自定义策略脚本的参数声明（对应 backend/strategies/*.py 的 PARAMS）。 */
export interface StrategyParam {
  name: string
  label: string
  default: number
  min: number | null
  max: number | null
}

export interface StrategyInfo {
  id: string
  name: string
  description: string
  params: StrategyParam[]
  error?: string | null
}

export interface BacktestPayload {
  symbol: string
  start: string
  end: string
  init_cash: number
  cost_model: string
  signal: { type: string; fast: number; slow: number; n: number }
  strategy?: { id: string; params: Record<string, number> } | null
  money: { type: string; n: number; percent: number }
  overlays: { type: string; n: number; key?: string | null }[]
  stoploss?: number | null
  takeprofit?: number | null
  slippage?: number | null
}
