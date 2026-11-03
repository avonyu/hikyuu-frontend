import { useEffect, useRef } from 'react'
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
import type { Candle, Trade } from '../lib/types'

interface Props {
  candles: Candle[]
  overlays?: Record<string, number[]>
  trades?: Trade[]
  height?: number
}

const UP = '#f85149' // A 股：红涨
const DOWN = '#3fb950' // 绿跌
const GRID = '#21262d'
const TEXT = '#8b949e'

const OVERLAY_COLORS = ['#58a6ff', '#d29922', '#a371f7', '#39c5cf', '#f778ba']

/**
 * K 线图，含成交量、指标叠加线与买卖点标记。
 *
 * lightweight-charts v5 的 API 与 v4 不同：
 * - 序列统一用 chart.addSeries(SeriesType, options) 创建
 * - 标记是 primitive，用 createSeriesMarkers(series, [...])
 * - 时间为 UTC 秒或 'YYYY-MM-DD' 字符串，不能混用
 */
export default function KlineChart({
  candles,
  overlays = {},
  trades = [],
  height = 420,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null)
  const overlaySeriesRef = useRef<ISeriesApi<'Line'>[]>([])

  // 图表只创建一次，数据变化时用 setData 更新
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const chart = createChart(container, {
      height,
      layout: {
        background: { color: 'transparent' },
        textColor: TEXT,
        fontSize: 11,
      },
      grid: {
        vertLines: { color: GRID },
        horzLines: { color: GRID },
      },
      rightPriceScale: { borderColor: GRID },
      timeScale: { borderColor: GRID, rightOffset: 4 },
      crosshair: {
        mode: 0,
        vertLine: { color: '#484f58', width: 1, style: 3 },
        horzLine: { color: '#484f58', width: 1, style: 3 },
      },
      localization: {
        locale: 'zh-CN',
      },
    })

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: UP,
      downColor: DOWN,
      borderUpColor: UP,
      borderDownColor: DOWN,
      wickUpColor: UP,
      wickDownColor: DOWN,
    })

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    })
    chart
      .priceScale('volume')
      .applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })

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
  }, [height])

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
        color: c.close >= c.open ? `${UP}40` : `${DOWN}40`,
      })),
    )
    chart.timeScale().fitContent()
  }, [candles])

  // 指标叠加线：每次先移除上一次创建的 series，否则重复回测会不断叠加
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return

    overlaySeriesRef.current.forEach((series) => chart.removeSeries(series))
    overlaySeriesRef.current = []

    Object.entries(overlays).forEach(([, values], idx) => {
      const color = OVERLAY_COLORS[idx % OVERLAY_COLORS.length]
      const line = chart.addSeries(LineSeries, {
        color,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      })
      const points = candles
        .map((c, i) => ({ time: c.time as Time, value: values[i] }))
        .filter((p) => Number.isFinite(p.value))
      line.setData(points)
      overlaySeriesRef.current.push(line)
    })
  }, [overlays, candles])

  // 买卖点标记
  useEffect(() => {
    const series = candleSeriesRef.current
    if (!series) return

    const markers: SeriesMarkerBar<Time>[] = trades
      .filter((t) => t.business === 'BUY' || t.business === 'SELL')
      .map((t) => ({
        time: t.datetime.slice(0, 10) as Time,
        position: t.business === 'BUY' ? ('belowBar' as const) : ('aboveBar' as const),
        color: t.business === 'BUY' ? UP : DOWN,
        shape: t.business === 'BUY' ? ('arrowUp' as const) : ('arrowDown' as const),
      }))
      .sort((a, b) => String(a.time).localeCompare(String(b.time)))

    if (markersRef.current) {
      markersRef.current.setMarkers(markers)
    } else {
      markersRef.current = createSeriesMarkers(series, markers)
    }
  }, [trades])

  return <div ref={containerRef} style={{ width: '100%', height }} />
}
