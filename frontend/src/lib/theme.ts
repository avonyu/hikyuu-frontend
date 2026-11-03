import { createContext, useContext, useMemo } from 'react'

export type Theme = 'light' | 'dark'

export const THEME_STORAGE_KEY = 'hikyuu-theme'

export interface ThemeContextValue {
  theme: Theme
  setTheme: (theme: Theme) => void
  toggle: () => void
}

export const ThemeContext = createContext<ThemeContextValue | null>(null)

export function readInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'dark'
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY)
  if (stored === 'light' || stored === 'dark') return stored
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme 必须在 ThemeProvider 内使用')
  return ctx
}

export interface ChartPalette {
  grid: string
  text: string
  up: string
  down: string
  line: string
  baseline: string
  volumeUp: string
  volumeDown: string
}

const CHART_PALETTES: Record<Theme, ChartPalette> = {
  dark: {
    grid: '#262626',
    text: '#a1a1aa',
    up: '#f87171',
    down: '#4ade80',
    line: '#93c5fd',
    baseline: '#525252',
    volumeUp: '#f8717166',
    volumeDown: '#4ade8066',
  },
  light: {
    grid: '#e5e5e5',
    text: '#737373',
    up: '#dc2626',
    down: '#16a34a',
    line: '#2563eb',
    baseline: '#a3a3a3',
    volumeUp: '#dc262666',
    volumeDown: '#16a34a66',
  },
}

/** 图表等非 CSS 场景用的配色 */
export function useChartTheme(): ChartPalette {
  const { theme } = useTheme()
  return useMemo(() => CHART_PALETTES[theme], [theme])
}
