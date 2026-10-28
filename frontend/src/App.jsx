
import React, { useCallback, useEffect, useRef, useState } from 'react'
import {
  createChart,
  CandlestickSeries,
  ColorType,
} from 'lightweight-charts'

const API = (
  import.meta.env.VITE_API_URL || 'https://marketforge-api-1ivz.onrender.com'
).replace(/\/$/, '')

const CHART_LIMIT = 3000

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
        time: Number(c.time),
        open: Number(c.open),
        high: Number(c.high),
        low: Number(c.low),
        close: Number(c.close),
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
  if (!Array.isArray(points) || points.length < 2) {
    return (
      <div className="equity-section">
        <div className="equity-heading">EQUITY CURVE</div>
        <p className="muted">Not enough equity data to display.</p>
      </div>
    )
  }

  const width = 600
  const height = 180
  const pad = 14

  const values = points
    .map((p) => Number(p.equity))
    .filter(Number.isFinite)

  if (values.length < 2) {
    return (
      <div className="equity-section">
        <div className="equity-heading">EQUITY CURVE</div>
        <p className="muted">Equity data is unavailable.</p>
      </div>
    )
  }

  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1

  const coords = values
    .map((value, i) => {
      const x =
        pad + (i / (values.length - 1)) * (width - pad * 2)
      const y =
        height -
        pad -
        ((value - min) / range) * (height - pad * 2)

      return `${x},${y}`
    })
    .join(' ')

  return (
    <div className="equity-section">
      <div className="equity-heading">
        <span>EQUITY CURVE</span>
        <span>{values.length} points</span>
      </div>

      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Backtest account equity curve"
        className="equity-chart"
      >
        <line
          x1={pad}
          y1={height / 2}
          x2={width - pad}
          y2={height / 2}
          stroke="#293142"
          strokeDasharray="4 4"
        />
        <polyline
          points={coords}
          fill="none"
          stroke="#26a69a"
          strokeWidth="2"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      </svg>

      <div className="equity-range">
        <span>Low: ${fmt(min)}</span>
        <span>High: ${fmt(max)}</span>
      </div>
    </div>
  )
}

function TradeTable({ trades }) {
  if (!Array.isArray(trades) || !trades.length) {
    return <p className="muted">No closed trades in this test.</p>
  }

  return (
    <div className="trade-table-wrap">
      <table className="trade-table">
        <thead>
          <tr>
            <th>Entry</th>
            <th>Exit</th>
            <th>Buy price</th>
            <th>Sell price</th>
            <th>P/L</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {[...trades].reverse().map((trade, i) => (
            <tr
              key={`${trade.entry_time}-${trade.exit_time}-${i}`}
            >
              <td>
                {trade.entry_time
                  ? new Date(
                      Number(trade.entry_time) * 1000
                    ).toLocaleString()
                  : '—'}
              </td>
              <td>
                {trade.exit_time
                  ? new Date(
                      Number(trade.exit_time) * 1000
                    ).toLocaleString()
                  : '—'}
              </td>
              <td>{fmt(trade.entry)}</td>
              <td>{fmt(trade.exit)}</td>
              <td
                className={
                  Number(trade.pnl) >= 0
                    ? 'positive'
                    : 'negative'
                }
              >
                {Number(trade.pnl) >= 0 ? '+' : ''}$
                {fmt(trade.pnl)}
                <div className="trade-percent">
                  {fmt(trade.return_pct)}%
                </div>
              </td>
              <td>
                {trade.exit_reason ||
                  trade.note ||
                  'Signal exit'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function App() {
  const [symbol, setSymbol] = useState('XAUUSD')
  const [timeframe, setTimeframe] = useState('15m')
  const [candles, setCandles] = useState([])
  const [source, setSource] = useState('Connecting…')
  const [sourceType, setSourceType] = useState('unknown')
  const [totalCandles, setTotalCandles] = useState(0)
  const [fast, setFast] = useState(9)
  const [slow, setSlow] = useState(21)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [loadingCandles, setLoadingCandles] = useState(false)
  const [error, setError] = useState('')

  const last = candles[candles.length - 1]
  const isHistorical = sourceType === 'historical_csv'

  const loadCandles = useCallback(async () => {
    setLoadingCandles(true)
    setError('')

    try {
      const url =
        `${API}/api/candles?symbol=${encodeURIComponent(symbol)}` +
        `&timeframe=${encodeURIComponent(timeframe)}` +
        `&limit=${CHART_LIMIT}`

      const response = await fetch(url)
      const data = await response.json()

      if (!response.ok) {
        throw new Error(
          data.detail ||
            `Backend response error (${response.status})`
        )
      }

      const rows = Array.isArray(data.candles)
        ? data.candles
        : []

      if (!rows.length) {
        throw new Error('The API returned no candles.')
      }

      setCandles(rows)
      setSourceType(data.source || 'unknown')
      setSource(
        data.source === 'historical_csv'
          ? 'HISTORICAL CSV'
          : data.source === 'synthetic_demo'
            ? 'DEMO DATA'
            : 'Connected'
      )

      // Ask the API which historical datasets are currently loaded.
      let healthCount = 0

      try {
        const healthResponse = await fetch(`${API}/api/health`)

        if (healthResponse.ok) {
          const health = await healthResponse.json()
          const datasets = Array.isArray(
            health.uploaded_datasets
          )
            ? health.uploaded_datasets
            : []

          const match = datasets.find((item) =>
            (typeof item === 'string' ? item : item.key) ===
            `${symbol.toUpperCase()}:${timeframe}`
          )

          healthCount =
            typeof match === 'object' && match
              ? Number(match.candles || 0)
              : 0
        }
      } catch {
        // Chart data can load even if the health count is unavailable.
      }

      setTotalCandles(
        Number(
          data.total_candles ||
            data.candles_total ||
            healthCount ||
            rows.length
        )
      )
    } catch (e) {
      setCandles([])
      setSource('Offline')
      setSourceType('unknown')
      setTotalCandles(0)
      setError(`Cannot load candles: ${e.message}`)
    } finally {
      setLoadingCandles(false)
    }
  }, [symbol, timeframe])

  useEffect(() => {
    loadCandles()
  }, [loadCandles])

  async function runBacktest() {
    if (Number(fast) >= Number(slow)) {
      setError('Fast period must be smaller than slow period.')
      return
    }

    setBusy(true)
    setError('')
    setResult(null)

    try {
      const response = await fetch(`${API}/api/backtest`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          symbol,
          timeframe,
          fast_period: Number(fast),
          slow_period: Number(slow),
          initial_balance: 10000,
          fee_bps: 2,
        }),
      })

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail || 'Backtest failed')
      }

      setResult(data)
    } catch (e) {
      setError(e.message || 'Backtest failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">M</span>
          <span>
            MARKET<span className="accent">FORGE</span>
          </span>
          <small>ANALYTICS</small>
        </div>

        <div className="top-actions">
          <span className="status-dot" />
          <span>{source}</span>
          <button
            onClick={loadCandles}
            disabled={loadingCandles}
          >
            {loadingCandles ? 'Loading…' : '↻ Refresh'}
          </button>
        </div>
      </header>

      <div className="toolbar">
        <select
          value={symbol}
          onChange={(e) => {
            setSymbol(e.target.value)
            setResult(null)
          }}
        >
          <option value="XAUUSD">XAUUSD · Gold</option>
          <option value="BTCUSD">BTCUSD · Bitcoin</option>
          <option value="EURUSD">
            EURUSD · Euro / US Dollar
          </option>
        </select>

        <div className="tf-list">
          {['1m', '5m', '15m', '30m', '1h', '4h', '1d'].map(
            (tf) => (
              <button
                className={timeframe === tf ? 'selected' : ''}
                key={tf}
                onClick={() => {
                  setTimeframe(tf)
                  setResult(null)
                }}
              >
                {tf}
              </button>
            )
          )}
        </div>

        <span className="tool-separator" />

        <button
          title="Indicators"
          onClick={() =>
            setError('Indicators are not connected yet.')
          }
        >
          ƒx Indicators
        </button>

        <button
          title="Drawing tools"
          onClick={() =>
            setError('Drawing tools are not connected yet.')
          }
        >
          ╱ Draw
        </button>
      </div>

      <main className="workspace">
        <section className="chart-panel">
          <div className="chart-heading">
            <div>
              <div className="instrument">
                {symbol}{' '}
                <span className="muted">· {timeframe}</span>
              </div>
              <div className="subheading">
                Candlestick chart{' '}
                <span className="tag">
                  {isHistorical
                    ? 'HISTORICAL CSV'
                    : sourceType === 'synthetic_demo'
                      ? 'DEMO'
                      : 'NO DATA'}
                </span>
              </div>
            </div>

            <div className="price-block">
              <strong>{last ? fmt(last.close) : '—'}</strong>
              <span
                className={
                  last && last.close >= last.open
                    ? 'positive'
                    : 'negative'
                }
              >
                {last
                  ? `${last.close >= last.open ? '+' : ''}${fmt(
                      last.close - last.open
                    )}`
                  : '—'}
              </span>
            </div>
          </div>

          {candles.length ? (
            <CandleChart candles={candles} />
          ) : (
            <div className="empty-chart">
              {loadingCandles
                ? 'Loading candles…'
                : 'No candle data available.'}
            </div>
          )}

          <div className="chart-footer">
            <span>
              {isHistorical
                ? 'Historical CSV feed'
                : 'Demo feed — not live prices'}
            </span>
            <span>UTC timestamps</span>
            <span>
              {candles.length.toLocaleString()} candles shown
              {totalCandles > candles.length
                ? ` · ${totalCandles.toLocaleString()} total in dataset`
                : ''}
            </span>
          </div>
        </section>

        <aside className="side-panel">
          <div className="panel-title">
            STRATEGY LAB <span className="live-pill">BETA</span>
          </div>

          <p className="muted intro">
            Run a basic Python SMA crossover backtest using the
            selected symbol and timeframe's uploaded historical
            dataset.
          </p>

          <label>
            Fast SMA period
            <input
              type="number"
              min="2"
              max="200"
              value={fast}
              onChange={(e) => setFast(e.target.value)}
            />
          </label>

          <label>
            Slow SMA period
            <input
              type="number"
              min="3"
              max="500"
              value={slow}
              onChange={(e) => setSlow(e.target.value)}
            />
          </label>

          <button
            className="primary-button"
            disabled={
              busy ||
              loadingCandles ||
              Number(fast) < 2 ||
              Number(slow) < 3 ||
              Number(fast) >= Number(slow)
            }
            onClick={runBacktest}
          >
            {busy ? 'Testing…' : '▶ Run Backtest'}
          </button>

          {Number(fast) >= Number(slow) && (
            <p className="error">
              Fast period must be smaller than slow period.
            </p>
          )}

          {result && (
            <div className="results">
              <div className="result-grid">
                <div className="metric">
                  <small>NET RETURN</small>
                  <strong
                    className={
                      Number(result.net_return_pct) >= 0
                        ? 'positive'
                        : 'negative'
                    }
                  >
                    {fmt(result.net_return_pct)}%
                  </strong>
                </div>

                <div className="metric">
                  <small>WIN RATE</small>
                  <strong>{fmt(result.win_rate_pct)}%</strong>
                </div>

                <div className="metric">
                  <small>TRADES</small>
                  <strong>{fmt(result.trades)}</strong>
                </div>

                <div className="metric">
                  <small>MAX DRAWDOWN</small>
                  <strong className="negative">
                    {fmt(result.max_drawdown_pct)}%
                  </strong>
                </div>
              </div>

              <EquityCurve points={result.equity_curve} />

              <div className="balance-row">
                <span>Initial balance</span>
                <strong>${fmt(result.initial_balance)}</strong>
              </div>

              <div className="balance-row">
                <span>Ending balance</span>
                <strong>${fmt(result.final_balance)}</strong>
              </div>

              <div className="trade-head">TRADE DETAILS</div>

              <TradeTable trades={result.trade_list} />

              <p className="fine-print">
                Source: {result.data_source || 'API response'}.
                Historical backtest results are estimates, not
                guarantees. Fees are approximated; spread, slippage,
                financing, and intrabar execution may not be fully
                modeled.
              </p>
            </div>
          )}

          <div className="editor-preview">
            <div className="editor-title">
              STRATEGY SOURCE <span>Python engine</span>
            </div>

            <pre>{`# SMA crossover (placeholder)
fast = SMA(close, ${fast || 9})
slow = SMA(close, ${slow || 21})
if crossover(fast, slow):
    enter_long()
if crossunder(fast, slow):
    exit_long()`}</pre>

            <div className="muted tiny">
              Preview only — this editor is not yet an executable
              Pine Script editor.
            </div>
          </div>
        </aside>
      </main>

      {error && (
        <div className="toast" role="alert">
          {error}
          <button onClick={() => setError('')}>×</button>
        </div>
      )}

      <footer>
        <span>MarketForge · Backtest UI</span>
        <span>Market data: {source} · No orders are sent</span>
      </footer>
    </div>
  )
}
