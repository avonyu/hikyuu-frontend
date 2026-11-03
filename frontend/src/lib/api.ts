import type {
  BacktestPayload,
  Health,
  Job,
  Meta,
  StrategyInfo,
  SymbolInfo,
} from './types'

const BASE = '/api'

/** 把 FastAPI 的错误响应整理成一句可读的话。 */
function errorMessage(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  // 校验错误（422）是 {loc, msg} 数组，直接当字符串会显示 [object Object]
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        const entry = item as { loc?: unknown[]; msg?: string }
        const field = Array.isArray(entry.loc) ? entry.loc[entry.loc.length - 1] : undefined
        return entry.msg ? (field ? `${String(field)}: ${entry.msg}` : entry.msg) : null
      })
      .filter(Boolean)
    if (parts.length > 0) return parts.join('；')
  }
  return fallback
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = errorMessage(await res.json(), detail)
    } catch {
      /* 响应体不是 JSON 时保留状态文本 */
    }
    throw new Error(detail)
  }
  // 204 / 空响应体没有 JSON，直接解析会抛错
  const text = await res.text()
  return (text ? JSON.parse(text) : null) as T
}

export function fetchHealth() {
  return request<Health>('/health')
}

export function fetchMeta() {
  return request<Meta>('/meta')
}

export function fetchSymbols() {
  return request<SymbolInfo[]>('/symbols')
}

export function fetchStrategies() {
  return request<StrategyInfo[]>('/strategies')
}

/**
 * 只算指标叠加线，不跑回测。
 *
 * 勾选指标后调用它即可实时重画叠加线，值与回测结果里的完全一致。
 */
export function fetchOverlays(payload: {
  symbol: string
  start: string
  end: string
  overlays: { type: string; n: number; key?: string | null }[]
}) {
  return request<Record<string, number[]>>('/overlays', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function refreshSymbols() {
  return request<{ refreshed: number; results: unknown[] }>('/symbols/refresh', {
    method: 'POST',
  })
}

export function submitBacktest(payload: BacktestPayload) {
  return request<{ id: string; status: string }>('/backtests', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchJob(id: string) {
  return request<Job>(`/backtests/${id}`)
}

/** 轮询直到任务结束。回测通常在百毫秒内完成。 */
export async function pollJob(
  id: string,
  onUpdate?: (job: Job) => void,
  intervalMs = 200,
  timeoutMs = 60_000,
): Promise<Job> {
  const deadline = Date.now() + timeoutMs
  for (;;) {
    const job = await fetchJob(id)
    onUpdate?.(job)
    if (job.status === 'done' || job.status === 'error') return job
    if (Date.now() > deadline) {
      throw new Error('回测超时')
    }
    await new Promise((r) => setTimeout(r, intervalMs))
  }
}
