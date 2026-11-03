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

/** 回测设置表单的完整配置（会被持久化到 localStorage）。 */
export interface StrategyConfig {
  symbol: string
  start: string
  end: string
  init_cash: number
  cost_model: string
  strategyId: string
  strategyParams: Record<string, number>
  moneyType: 'fixed_count' | 'fixed_percent'
  count: number
  percent: number
  overlays: { type: string; n: number }[]
  stoploss: number | null
  takeprofit: number | null
  slippage: number | null
}

export interface BacktestResult {
  symbol: string
  start: string
  end: string
  init_cash: number
  cost_model: string
  metrics: Record<string, number>
  candles: Candle[]
  /** 资金曲线：自带日期，与 candles 一一对应 */
  equity: { time: string; value: number }[]
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

/** 引擎状态机：idle（未加载）| loading（加载中）| ready（就绪）| error（加载失败） */
export type EngineState = 'idle' | 'loading' | 'ready' | 'error'

export interface Health {
  status: string
  engine_ready: boolean
  /** 引擎状态机；旧版后端可能不返回，用 engine_ready 兜底 */
  engine_state?: EngineState
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
  /** 整数参数（脚本里 default 写成 int）；否则为小数参数 */
  integer: boolean
}

export interface StrategyInfo {
  id: string
  name: string
  description: string
  params: StrategyParam[]
  error?: string | null
  /** 脚本自带资金管理：表单里的「资金管理」设置对它不生效 */
  money_manager?: boolean
}

export interface BacktestPayload {
  symbol: string
  start: string
  end: string
  init_cash: number
  cost_model: string
  strategy: { id: string; params: Record<string, number> }
  money: { type: string; n: number; percent: number }
  overlays: { type: string; n: number; key?: string | null }[]
  stoploss?: number | null
  takeprofit?: number | null
  slippage?: number | null
}
