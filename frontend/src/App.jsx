
import React, { useEffect, useRef, useState } from 'react'
import {
  createChart,
  CandlestickSeries,
  ColorType,
} from 'lightweight-charts'

const API = (
  import.meta.env.VITE_API_URL || 'https://marketforge-api-1ivz.onrender.com'
).replace(/\/$/, '')

const fmt = (n) =>
  Number(n ?? 0).toLocaleString(undefined, {
    maximumFractionDigits: 2,
  })

function CandleChart({ candles }) {
  const host = useRef(null)

  useEffect(() => {
    if (!host.current || !candles.length) return

    const chart = createChart(host.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#0b0e14' },
        textColor: '#aab3c5',
      },
      grid: {
        vertLines: { color: '#171d29' },
        horzLines: { color: '#171d29' },
      },
      rightPriceScale: { borderColor: '#293142' },
      timeScale: {
        borderColor: '#293142',
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: {
        vertLine: { color: '#69758b' },
        horzLine: { color: '#69758b' },
      },
      width: host.current.clientWidth,
      height: host.current.clientHeight,
    })

    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderUpColor: '#26a69a',
      borderDownColor: '#ef5350',
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
    })

    series.setData(
      candles.map((c) => ({
        time: c.time,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }))
    )

    chart.timeScale().fitContent()

    const onResize = () => {
      if (host.current) {
        chart.applyOptions({
          width: host.current.clientWidth,
        })
      }
    }

    window.addEventListener('resize', onResize)

    return () => {
      window.removeEventListener('resize', onResize)
      chart.remove()
    }
  }, [candles])

  return <div ref={host} className="chart-host" />
}

function EquityCurve({ points }) {
  if (!points || points.length < 2) {
    return (
      <div className="equity-section">
        <div className="equity-heading">EQUITY CURVE</div>
        <p className="muted">
          Not enough equity data to display.
        </p>
      </div>
    )
