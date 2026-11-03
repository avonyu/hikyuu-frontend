import { useEffect, useRef } from 'react'
import {
  AreaSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from 'lightweight-charts'
import { useChartTheme } from '@/lib/theme'

interface Props {
  candles: { time: string }[]
  equity: number[]
  initCash: number
  height?: number
}

/** 资金曲线（权益曲线）。 */
export default function EquityChart({ candles, equity, initCash, height = 220 }: Props) {
  const palette = useChartTheme()
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
      localization: { locale: 'zh-CN' },
    })

    const areaSeries = chart.addSeries(AreaSeries, {
      lineColor: palette.line,
      topColor: `${palette.line}47`,
      bottomColor: `${palette.line}05`,
      lineWidth: 2,
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
  }, [height, palette])

  useEffect(() => {
    const chart = chartRef.current
    const series = seriesRef.current
    if (!chart || !series) return

    // 资金曲线与 K 线等长且等日期，按索引对齐
    const points = candles
      .map((c, i) => ({ time: c.time as Time, value: equity[i] }))
      .filter((p) => Number.isFinite(p.value))
    series.setData(points)

    // 初始资金基准线：先清掉上一次创建的，避免重复回测叠加
    series.priceLines().forEach((line) => series.removePriceLine(line))
    series.createPriceLine({
      price: initCash,
      color: palette.baseline,
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: true,
      title: '初始资金',
    })

    chart.timeScale().fitContent()
  }, [candles, equity, initCash, palette])

  return <div ref={containerRef} style={{ width: '100%', height }} />
}
