            disabled={busy || Number(fast) >= Number(slow)}
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
                      result.net_return_pct >= 0
                        ? 'positive'
                        : 'negative'
                    }
                  >
                    {result.net_return_pct}%
                  </strong>
                </div>

                <div className="metric">
                  <small>WIN RATE</small>
                  <strong>{result.win_rate_pct}%</strong>
                </div>

                <div className="metric">
                  <small>TRADES</small>
                  <strong>{result.trades}</strong>
                </div>

                <div className="metric">
                  <small>MAX DRAWDOWN</small>
                  <strong className="negative">
                    {result.max_drawdown_pct}%
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
                {result.data_source === 'historical_csv'
                  ? `Historical CSV test · ${fmt(result.candles_tested)} candles. This is a simulation, not a guarantee of future results. Spread, slippage, financing and intrabar execution may not be fully modeled.`
                  : 'Demo data only; not real market performance. Spread, slippage, financing and intrabar stops are not fully modeled.'}
              </p>
            </div>
          )}

          <div className="editor-preview">
            <div className="editor-title">
              STRATEGY SOURCE <span>Python engine</span>
            </div>

            <pre>{`# SMA crossover (demo)
fast = SMA(close, ${fast || 9})
slow = SMA(close, ${slow || 21})
if crossover(fast, slow):
    enter_long()
if crossunder(fast, slow):
    exit_long()`}</pre>

            <div className="muted tiny">
              Editor preview only — not yet an executable Pine-like language.
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
        <span>MarketForge v0.2 · Backtest UI</span>
        <span>Market data: {source === 'historical_csv' ? 'Historical CSV' : source === 'synthetic_demo' ? 'Synthetic demo' : source} · No orders are sent</span>
      </footer>
    </div>
  )
}
