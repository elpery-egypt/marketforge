from datetime import datetime, timedelta, timezone
from math import sin, cos
import os
from typing import Literal
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from .strategy import run_sma_backtest

app = FastAPI(title="MarketForge API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

Timeframe = Literal["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
STEP_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}

class BacktestRequest(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: Timeframe = "15m"
    fast_period: int = Field(default=9, ge=2, le=200)
    slow_period: int = Field(default=21, ge=3, le=500)
    initial_balance: float = Field(default=10000, gt=0)
    fee_bps: float = Field(default=2, ge=0, le=100)

@app.get("/api/health")
def health():
    return {"status": "ok", "app": "MarketForge API", "data_mode": "synthetic_demo"}

@app.get("/api/candles")
def candles(symbol: str = "XAUUSD", timeframe: Timeframe = "15m", limit: int = 500):
    if not 50 <= limit <= 3000:
        raise HTTPException(400, "limit must be between 50 and 3000")
    step = STEP_MINUTES[timeframe]
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    # Synthetic, repeatable-looking demonstration series. Never represents live prices.
    base = 2350.0 if symbol.upper() == "XAUUSD" else 100.0
    rows = []
    price = base
    start = now - timedelta(minutes=step * limit)
    for i in range(limit):
        t = start + timedelta(minutes=step * i)
        trend = 0.025 * sin(i / 37) + 0.008 * cos(i / 13)
        change = trend + 0.006 * sin(i * 1.71) + 0.004 * cos(i * 0.43)
        o = price
        c = max(0.01, o * (1 + change / 100))
        wick = o * (0.0012 + abs(sin(i * 0.91)) * 0.001)
        h = max(o, c) + wick
        l = max(0.01, min(o, c) - wick * 0.85)
        rows.append({
            "time": int(t.timestamp()),
            "open": round(o, 4), "high": round(h, 4),
            "low": round(l, 4), "close": round(c, 4),
            "volume": int(100 + abs(sin(i * 0.4)) * 900)
        })
        price = c
    return {"symbol": symbol.upper(), "timeframe": timeframe, "source": "synthetic_demo", "candles": rows}

@app.post("/api/backtest")
def backtest(req: BacktestRequest):
    if req.fast_period >= req.slow_period:
        raise HTTPException(400, "fast_period must be smaller than slow_period")
    data = candles(req.symbol, req.timeframe, 1000)["candles"]
    return run_sma_backtest(
        data, req.fast_period, req.slow_period,
        req.initial_balance, req.fee_bps
    )
