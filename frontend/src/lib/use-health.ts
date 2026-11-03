import { useCallback, useEffect, useRef, useState } from 'react'

import { fetchHealth } from './api'
import type { EngineState, Health } from './types'

/** 轮询间隔。引擎是懒加载的，短间隔才能让指示标志及时变化。 */
const POLL_INTERVAL_MS = 2000

export interface UseHealthResult {
  /** 后端上报的引擎状态；请求失败时为 offline（后端不可达） */
  state: EngineState | 'offline'
  /** 最近一次成功拉取的健康信息 */
  health: Health | null
  /** 最近一次拉取的错误信息 */
  error: string | null
  /** 立即刷新一次（如回测结束后调用） */
  refresh: () => void
}

/**
 * 轮询 /api/health，实时反映引擎状态。
 *
 * 引擎在首次回测时才懒加载，仅在挂载时取一次会导致指示标志停留在「待加载」，
 * 因此这里按固定间隔轮询，并在页面重新可见时立即补一次。
 */
export function useHealth(intervalMs = POLL_INTERVAL_MS): UseHealthResult {
  const [health, setHealth] = useState<Health | null>(null)
  const [state, setState] = useState<EngineState | 'offline'>('idle')
  const [error, setError] = useState<string | null>(null)
  const aliveRef = useRef(true)

  const refresh = useCallback(async () => {
    try {
      const next = await fetchHealth()
      if (!aliveRef.current) return
      setHealth(next)
      // 兼容未返回 engine_state 的旧后端
      setState(next.engine_state ?? (next.engine_ready ? 'ready' : 'idle'))
      setError(null)
    } catch (e) {
      if (!aliveRef.current) return
      setState('offline')
      setError(e instanceof Error ? e.message : '无法连接后端服务')
    }
  }, [])

  useEffect(() => {
    aliveRef.current = true

    const timer = setInterval(() => {
      // 后台标签页不轮询，回到前台时补一次
      if (document.visibilityState === 'hidden') return
      void refresh()
    }, intervalMs)

    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') void refresh()
    }
    document.addEventListener('visibilitychange', onVisibilityChange)

    // 首次拉取放在定时器回调里，避免在 effect 中同步写状态
    const first = setTimeout(() => void refresh(), 0)

    return () => {
      aliveRef.current = false
      clearTimeout(first)
      clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [refresh, intervalMs])

  return { state, health, error, refresh }
}
