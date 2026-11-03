import { useEffect, useMemo, useRef } from 'react'
import {
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarkerBar,
  type Time,
} from 'lightweight-charts'
import { useChartTheme } from '@/lib/theme'
import type { Candle, Trade } from '../lib/types'

interface Props {
  candles: Candle[]
  overlays?: Record<string, number[]>
  trades?: Trade[]
  height?: number
}

/**
 * 叠加线配色按指标类型固定，而不是按序号。
 *
 * 实时增删指标时若按序号取色，删掉一条会让其余线的颜色全部错位。
 */
const OVERLAY_COLORS: Record<string, string | string[]> = {
  ma: '#3b82f6',
  ema: '#eab308',
  rsi: '#a855f7',
  macd: ['#06b6d4', '#22c55e', '#ec4899'],
}

/** key 形如 ma20 / ema12 / macd12_diff */
function overlayColor(key: string): string {
  const type = key.split(/[0-9]/)[0]
  const palette = OVERLAY_COLORS[type]
  if (!palette) return '#94a3b8'
  if (typeof palette === 'string') return palette
  // MACD 有三条线（BAR / DIFF / DEA），按后缀区分
  if (key.endsWith('_diff')) return palette[1]
  if (key.endsWith('_dea')) return palette[2]
  return palette[0]
}

/**
 * 指标分组：MA/EMA 画在主图（与价格同轴），
 * RSI（0~100）与 MACD（围绕 0）量纲不同，画在各自的副窗格里，
 * 否则会把价格轴撑坏。
 */
type OverlayGroup = 'price' | 'rsi' | 'macd'

function overlayGroup(key: string): OverlayGroup {
  const type = key.split(/[0-9]/)[0]
  if (type === 'rsi') return 'rsi'
  if (type === 'macd') return 'macd'
  return 'price'
}

/** 副窗格高度（像素） */
const AUX_PANE_HEIGHT = 90

/**
 * K 线图，含成交量、指标叠加线与买卖点标记。
 *
 * lightweight-charts v5 的 API 与 v4 不同：
 * - 序列统一用 chart.addSeries(SeriesType, options) 创建
 * - 标记是 primitive，用 createSeriesMarkers(series, [...])
 * - 时间是 'YYYY-MM-DD' 字符串
 */
export default function KlineChart({
  candles,
  overlays = {},
  trades = [],
  height = 420,
}: Props) {
  const palette = useChartTheme()
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null)
  const overlaySeriesRef = useRef<ISeriesApi<'Line'>[]>([])

  // 副窗格数量决定图表总高度（容器要跟着长高，否则会溢出压住下方卡片）
  const auxPanes = useMemo(() => {
    const groups = new Set(Object.keys(overlays).map(overlayGroup))
    return (['rsi', 'macd'] as const).filter((g) => groups.has(g)).length
  }, [overlays])
  const totalHeight = height + auxPanes * AUX_PANE_HEIGHT

  // 主题或高度变化时重建图表；数据变化只 setData
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const chart = createChart(container, {
      height,
      layout: {
        background: { color: 'transparent' },
        textColor: palette.text,
        fontSize: 11,
      },
      grid: {
        vertLines: { color: palette.grid },
        horzLines: { color: palette.grid },
      },
      rightPriceScale: { borderColor: palette.grid },
      timeScale: { borderColor: palette.grid, rightOffset: 4 },
      crosshair: {
        mode: 0,
        vertLine: { color: palette.text, width: 1, style: 3 },
        horzLine: { color: palette.text, width: 1, style: 3 },
      },
      localization: {
        locale: 'zh-CN',
      },
    })

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: palette.up,
      downColor: palette.down,
      borderUpColor: palette.up,
      borderDownColor: palette.down,
      wickUpColor: palette.up,
      wickDownColor: palette.down,
    })

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    })
    chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })

    chartRef.current = chart
    candleSeriesRef.current = candleSeries
    volumeSeriesRef.current = volumeSeries

    const observer = new ResizeObserver(() => {
      chart.applyOptions({ width: container.clientWidth })
    })
    observer.observe(container)
    chart.applyOptions({ width: container.clientWidth })

    return () => {
      observer.disconnect()
      chart.remove()
      chartRef.current = null
      candleSeriesRef.current = null
      volumeSeriesRef.current = null
      markersRef.current = null
      overlaySeriesRef.current = []
    }
  }, [height, palette])

  // K 线 + 成交量
  useEffect(() => {
    const candleSeries = candleSeriesRef.current
    const volumeSeries = volumeSeriesRef.current
    const chart = chartRef.current
    if (!chart || !candleSeries || !volumeSeries) return

    candleSeries.setData(
      candles.map((c) => ({
        time: c.time as Time,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      })),
    )

    volumeSeries.setData(
      candles.map((c) => ({
        time: c.time as Time,
        value: c.volume,
        color: c.close >= c.open ? palette.volumeUp : palette.volumeDown,
      })),
    )
    chart.timeScale().fitContent()
  }, [candles, palette])

  // 指标叠加线：每次先移除上一次创建的 series，否则重复回测会不断叠加。
  // RSI / MACD 量纲与价格不同，单独开窗格显示。
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return

    overlaySeriesRef.current.forEach((series) => chart.removeSeries(series))
    overlaySeriesRef.current = []

    const entries = Object.entries(overlays)
    const groups: Record<OverlayGroup, [string, number[]][]> = {
      price: [],
      rsi: [],
      macd: [],
    }
    entries.forEach(([key, values]) => groups[overlayGroup(key)].push([key, values]))

    // 副窗格按 rsi → macd 的顺序排列
    const auxGroups = (['rsi', 'macd'] as const).filter((g) => groups[g].length > 0)
    const neededPanes = auxGroups.length + 1

    // 移除多余的窗格（从后往前删，避免索引错位）
    for (let i = chart.panes().length - 1; i >= neededPanes; i -= 1) {
      chart.removePane(i)
    }
    while (chart.panes().length < neededPanes) {
      chart.addPane(true)
    }

    const paneOf: Record<OverlayGroup, number> = { price: 0, rsi: 0, macd: 0 }
    auxGroups.forEach((g, i) => {
      paneOf[g] = i + 1
    })

    // 主图保持原高度，副窗格另加高度
    chart.applyOptions({ height: totalHeight })
    chart.panes().forEach((pane, i) => {
      if (i === 0) return
      pane.setHeight(AUX_PANE_HEIGHT)
    })

    entries.forEach(([key, values]) => {
      const line = chart.addSeries(
        LineSeries,
        {
          color: overlayColor(key),
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        },
        paneOf[overlayGroup(key)],
      )
      const points = candles
        .map((c, i) => ({ time: c.time as Time, value: values[i] }))
        .filter((p) => Number.isFinite(p.value))
      line.setData(points)
      overlaySeriesRef.current.push(line)
    })
  }, [overlays, candles, totalHeight])

  // 买卖点标记
  useEffect(() => {
    const series = candleSeriesRef.current
    if (!series) return

    const markers: SeriesMarkerBar<Time>[] = trades
      .filter((t) => t.business === 'BUY' || t.business === 'SELL')
      .map((t) => ({
        time: t.datetime.slice(0, 10) as Time,
        position: t.business === 'BUY' ? ('belowBar' as const) : ('aboveBar' as const),
        color: t.business === 'BUY' ? palette.up : palette.down,
        shape: t.business === 'BUY' ? ('arrowUp' as const) : ('arrowDown' as const),
      }))
      .sort((a, b) => String(a.time).localeCompare(String(b.time)))

    if (markersRef.current) {
      markersRef.current.setMarkers(markers)
    } else {
      markersRef.current = createSeriesMarkers(series, markers)
    }
  }, [trades, palette])

  return <div ref={containerRef} style={{ width: '100%', height: totalHeight }} />
}
