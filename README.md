# MarketForge — TradingView-like platform starter

A runnable starter for a web + Windows desktop market-analysis application.

## Included in this MVP
- React + Vite UI with dark trading-terminal layout
- TradingView Lightweight Charts for candlesticks
- FastAPI backend with demo OHLCV history endpoint
- Python SMA-crossover backtest endpoint with trade list and basic metrics
- Strategy editor with a deliberately small Pine-like example format
- Electron wrapper for packaging the web UI as a Windows desktop app
- Live-data adapter interface placeholder (not a real feed)

## Important boundaries
- The included candles are synthetic demo data, **not real XAUUSD quotes**.
- Live market data requires a data provider/broker API, credentials, and any necessary exchange/vendor licenses.
- Order execution is not implemented. This project does not place trades.
- Pine Script compatibility is not implemented. The editor currently accepts a small Python strategy configuration; full Pine Script requires a parser/runtime and substantial work.
- This is a starter, not a production-secure financial application.

## Requirements
- Python 3.11+
- Node.js 20+
- npm

## Run the backend
```bash
cd backend
python -m venv .venv
# Windows PowerShell:
.venv\\Scripts\\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Backend docs: http://127.0.0.1:8000/docs

## Run the web UI
Open a second terminal:
```bash
cd frontend
npm install
npm run dev
```
Open the URL Vite prints (usually http://localhost:5173).

## Windows desktop wrapper
After installing frontend dependencies:
```bash
cd frontend
npm run desktop
```
To build a Windows installer/package on Windows:
```bash
npm run build
npm run desktop:dist
```
Electron packaging may require platform-specific build tooling.

## API
- `GET /api/health`
- `GET /api/candles?symbol=XAUUSD&timeframe=15m&limit=500`
- `POST /api/backtest` JSON body:
```json
{
  "symbol": "XAUUSD",
  "timeframe": "15m",
  "fast_period": 9,
  "slow_period": 21,
  "initial_balance": 10000,
  "fee_bps": 2
}
```

## Suggested next phases
1. Connect a licensed historical/live market data provider.
2. Store normalized candles in PostgreSQL/TimescaleDB.
3. Add WebSocket streaming and reconnect handling.
4. Implement indicator registry and strategy runtime.
5. Build deterministic backtesting (spread, commission, slippage, intrabar stop/target rules).
6. Add user accounts, saved layouts, permissions, tests, monitoring and security review.
7. Add a Pine-like parser only after the strategy engine API stabilizes.


## Free iPhone Home Screen deployment

This project includes a Render Blueprint (`render.yaml`) for a static mobile frontend and a Python API, plus a basic PWA manifest and service worker. Push the project root to a GitHub repository, then in Render choose **New > Blueprint** and connect that repository. Review the two services before deploying. The frontend expects `VITE_API_URL` to point at the API service; update it if Render assigns a different API URL. The API's `CORS_ORIGINS` should contain the exact frontend URL (comma-separated if more than one) for a tighter configuration.

After the frontend is deployed, open its HTTPS URL in Safari on iPhone, tap **Share**, then **Add to Home Screen**, and confirm **Add**. The home-screen icon is a web app/PWA, not a native App Store app. Free hosting may sleep or have usage limits.

**Important:** current candles are synthetic demo data, not live XAUUSD market prices. Do not use them for live trading decisions.
