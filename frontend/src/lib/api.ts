import type {
  BacktestPayload,
  Health,
  Job,
  Meta,
  StrategyInfo,
  SymbolInfo,
} from './types'

const BASE = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      /* 响应体不是 JSON 时保留状态文本 */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
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
