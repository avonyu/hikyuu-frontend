import { useEffect, useRef } from 'react'
import {
  AreaSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from 'lightweight-charts'

interface Props {
  candles: { time: string }[]
  equity: number[]
  initCash: number
  height?: number
}

const GRID = '#21262d'
const TEXT = '#8b949e'
const LINE = '#58a6ff'

/** 资金曲线（权益曲线）。与 K 线共用时间轴。 */
export default function EquityChart({
  candles,
  equity,
  initCash,
  height = 220,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Area'> | null>(null)

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
      grid: { vertLines: { color: GRID }, horzLines: { color: GRID } },
      rightPriceScale: { borderColor: GRID },
      timeScale: { borderColor: GRID, rightOffset: 4 },
      crosshair: {
        mode: 0,
        vertLine: { color: '#484f58', width: 1, style: 3 },
        horzLine: { color: '#484f58', width: 1, style: 3 },
      },
      localization: { locale: 'zh-CN' },
    })

    const areaSeries = chart.addSeries(AreaSeries, {
      lineColor: LINE,
      topColor: 'rgba(88,166,255,0.28)',
      bottomColor: 'rgba(88,166,255,0.02)',
      lineWidth: 1,
      priceLineVisible: false,
    })

    chartRef.current = chart
    seriesRef.current = areaSeries

    const observer = new ResizeObserver(() => {
      chart.applyOptions({ width: container.clientWidth })
    })
    observer.observe(container)
    chart.applyOptions({ width: container.clientWidth })

    return () => {
      observer.disconnect()
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
    }
  }, [height])

  useEffect(() => {
    const chart = chartRef.current
    const series = seriesRef.current
    if (!chart || !series) return

    // 资金曲线与 K 线等长且等日期，按索引对齐
    const points = candles
      .map((c, i) => ({ time: c.time as Time, value: equity[i] }))
      .filter((p) => Number.isFinite(p.value))
    series.setData(points)

    // 初始资金基准线：先清掉上一次创建的，否则每次回测都会叠加一条
    // （按 priceLines() 清而不是存 ref，HMR / 图表重建后也不会漏）
    series.priceLines().forEach((line) => series.removePriceLine(line))
    series.createPriceLine({
      price: initCash,
      color: '#484f58',
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: true,
      title: '初始资金',
    })

    chart.timeScale().fitContent()
  }, [candles, equity, initCash])

  return <div ref={containerRef} style={{ width: '100%', height }} />
}
