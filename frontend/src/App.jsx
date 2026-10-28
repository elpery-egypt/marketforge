import React, { useEffect, useRef, useState } from 'react'
import { createChart, CandlestickSeries, HistogramSeries, ColorType } from 'lightweight-charts'

const API = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
const fmt = (n) => Number(n).toLocaleString(undefined, {maximumFractionDigits: 2})

function CandleChart({ candles }) {
  const host = useRef(null)
  useEffect(() => {
    if (!host.current || !candles.length) return
    const chart = createChart(host.current, {
      layout: { background: { type: ColorType.Solid, color: '#0b0e14' }, textColor: '#aab3c5' },
      grid: { vertLines: { color: '#171d29' }, horzLines: { color: '#171d29' } },
      rightPriceScale: { borderColor: '#293142' },
      timeScale: { borderColor: '#293142', timeVisible: true, secondsVisible: false },
      crosshair: { vertLine: { color: '#69758b' }, horzLine: { color: '#69758b' } },
      width: host.current.clientWidth, height: host.current.clientHeight,
    })
    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#26a69a', downColor: '#ef5350',
      borderUpColor: '#26a69a', borderDownColor: '#ef5350',
      wickUpColor: '#26a69a', wickDownColor: '#ef5350',
    })
    series.setData(candles.map(c => ({ time: c.time, open: c.open, high: c.high, low: c.low, close: c.close })))
    chart.timeScale().fitContent()
    const onResize = () => chart.applyOptions({ width: host.current?.clientWidth || 800 })
    window.addEventListener('resize', onResize)
    return () => { window.removeEventListener('resize', onResize); chart.remove() }
  }, [candles])
  return <div ref={host} className="chart-host" />
}

export default function App() {
  const [symbol, setSymbol] = useState('XAUUSD')
  const [timeframe, setTimeframe] = useState('15m')
  const [candles, setCandles] = useState([])
  const [source, setSource] = useState('Loading…')
  const [fast, setFast] = useState(9)
  const [slow, setSlow] = useState(21)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const last = candles[candles.length - 1]

  async function loadCandles() {
    setError('')
    try {
      const r = await fetch(`${API}/api/candles?symbol=${symbol}&timeframe=${timeframe}&limit=700`)
      if (!r.ok) throw new Error('Backend response error')
      const data = await r.json()
      setCandles(data.candles)
      setSource(data.source === 'synthetic_demo' ? 'DEMO DATA — NOT LIVE' : data.source)
    } catch (e) { setError('Cannot connect to backend. Start FastAPI on port 8000.'); setSource('Offline') }
  }
  useEffect(() => { loadCandles() }, [symbol, timeframe])

  async function runBacktest() {
    setBusy(true); setError('')
    try {
      const r = await fetch(`${API}/api/backtest`, {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({symbol, timeframe, fast_period:Number(fast), slow_period:Number(slow), initial_balance:10000, fee_bps:2})
      })
      const data = await r.json()
      if (!r.ok) throw new Error(data.detail || 'Backtest failed')
      setResult(data)
    } catch(e) { setError(e.message || 'Backtest failed') }
    finally { setBusy(false) }
  }

  return <div className="app-shell">
    <header className="topbar">
      <div className="brand"><span className="brand-mark">M</span><span>MARKET<span className="accent">FORGE</span></span><small>ANALYTICS</small></div>
      <div className="top-actions"><span className="status-dot"/><span>{source}</span><button onClick={loadCandles}>↻ Refresh</button></div>
    </header>
    <div className="toolbar">
      <select value={symbol} onChange={e=>setSymbol(e.target.value)}><option value="XAUUSD">XAUUSD · Gold</option><option value="BTCUSD">BTCUSD · Bitcoin</option><option value="EURUSD">EURUSD · Euro / US Dollar</option></select>
      <div className="tf-list">{['1m','5m','15m','30m','1h','4h','1d'].map(tf=><button className={timeframe===tf?'selected':''} key={tf} onClick={()=>setTimeframe(tf)}>{tf}</button>)}</div>
      <span className="tool-separator"/>
      <button title="Indicators">ƒx Indicators</button><button title="Drawing tools">╱ Draw</button>
    </div>
    <main className="workspace">
      <section className="chart-panel">
        <div className="chart-heading">
          <div><div className="instrument">{symbol} <span className="muted">· {timeframe}</span></div><div className="subheading">Candlestick chart <span className="tag">DEMO</span></div></div>
          <div className="price-block"><strong>{last ? fmt(last.close) : '—'}</strong><span className={last && last.close >= last.open ? 'positive':'negative'}>{last ? `${last.close >= last.open ? '+' : ''}${fmt(last.close-last.open)}` : '—'}</span></div>
        </div>
        {candles.length ? <CandleChart candles={candles}/> : <div className="empty-chart">Loading chart…</div>}
        <div className="chart-footer"><span>◉ Demo feed</span><span>UTC timestamps</span><span>{candles.length} candles loaded</span></div>
      </section>
      <aside className="side-panel">
        <div className="panel-title">STRATEGY LAB <span className="live-pill">BETA</span></div>
        <p className="muted intro">Run a basic Python SMA crossover backtest on the loaded demo sample.</p>
        <label>Fast SMA period<input type="number" min="2" max="200" value={fast} onChange={e=>setFast(e.target.value)}/></label>
        <label>Slow SMA period<input type="number" min="3" max="500" value={slow} onChange={e=>setSlow(e.target.value)}/></label>
        <button className="primary-button" disabled={busy || Number(fast)>=Number(slow)} onClick={runBacktest}>{busy?'Testing…':'▶ Run Backtest'}</button>
        {Number(fast)>=Number(slow) && <p className="error">Fast period must be smaller than slow period.</p>}
        {result && <div className="results">
          <div className="result-grid">
            <div className="metric"><small>NET RETURN</small><strong className={result.net_return_pct>=0?'positive':'negative'}>{result.net_return_pct}%</strong></div>
            <div className="metric"><small>WIN RATE</small><strong>{result.win_rate_pct}%</strong></div>
            <div className="metric"><small>TRADES</small><strong>{result.trades}</strong></div>
            <div className="metric"><small>MAX DRAWDOWN</small><strong className="negative">{result.max_drawdown_pct}%</strong></div>
          </div>
          <div className="balance-row"><span>Ending balance</span><strong>${fmt(result.final_balance)}</strong></div>
          <div className="trade-head">RECENT CLOSED TRADES</div>
          <div className="trade-list">{result.trade_list.slice(-8).reverse().map((t,i)=><div className="trade" key={i}><span>{new Date(t.entry_time*1000).toLocaleString()}</span><strong className={t.pnl>=0?'positive':'negative'}>{t.pnl>=0?'+':''}${fmt(t.pnl)}</strong></div>)}</div>
          <p className="fine-print">Illustrative result only. Synthetic data; excludes spread, slippage and financing. Not a performance claim.</p>
        </div>}
        <div className="editor-preview"><div className="editor-title">STRATEGY SOURCE <span>Python engine</span></div><pre>{`# SMA crossover (demo)\nfast = SMA(close, ${fast || 9})\nslow = SMA(close, ${slow || 21})\nif crossover(fast, slow):\n    enter_long()\nif crossunder(fast, slow):\n    exit_long()`}</pre><div className="muted tiny">Editor preview only — not yet an executable Pine-like language.</div></div>
      </aside>
    </main>
    {error && <div className="toast" role="alert">{error}<button onClick={()=>setError('')}>×</button></div>}
    <footer><span>MarketForge v0.1 · Starter build</span><span>Market data: {source} · No orders are sent</span></footer>
  </div>
}
