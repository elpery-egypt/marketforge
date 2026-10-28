from datetime import datetime, timedelta, timezone
from math import sin, cos
from pathlib import Path
import csv
import io
import os
from typing import Literal

from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .strategy import run_sma_backtest, run_fair_pricing_backtest


app = FastAPI(title="MarketForge API", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,"
            "https://marketforge-dy5y.onrender.com",
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

Timeframe = Literal["1m", "5m", "15m", "30m", "1h", "4h", "1d"]

STEP_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}

# Datasets are loaded into memory at startup.
uploaded_data: dict[str, dict] = {}

GOLD_CSV_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "xauusd-m15-bid-2023-01-01-2026-08-02(2).csv"
)


class BacktestRequest(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: Timeframe = "15m"
    strategy: Literal[
        "sma_crossover",
        "fair_pricing_reversion",
    ] = "sma_crossover"

    fast_period: int = Field(default=9, ge=2, le=200)
    slow_period: int = Field(default=21, ge=3, le=500)
    initial_balance: float = Field(default=10000, gt=0)
    fee_bps: float = Field(default=2, ge=0, le=100)

    ema_period: int = Field(default=50, ge=10, le=200)
    atr_period: int = Field(default=14, ge=5, le=50)
    stretch_atr: float = Field(default=0.8, ge=0.2, le=3.0)
    stop_atr: float = Field(default=1.5, ge=0.5, le=5.0)
    reward_risk: float = Field(default=1.0, ge=0.5, le=5.0)
    swing_lookback: int = Field(default=5, ge=2, le=20)


def parse_timestamp(value: str) -> int:
    value = value.strip()

    if not value:
        raise ValueError("Empty timestamp")

    try:
        number = float(value)
        if number > 100_000_000_000:
            number /= 1000
        if number > 0:
            return int(number)
    except ValueError:
        pass

    normalized = value.replace("Z", "+00:00")

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = None

    if parsed is None:
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%Y %H:%M",
            "%m/%d/%Y",
        ):
            try:
                parsed = datetime.strptime(value, fmt)
                break
            except ValueError:
                continue

    if parsed is None:
        raise ValueError(f"Unsupported timestamp: {value}")

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return int(parsed.timestamp())


def normalize_csv(contents: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(contents.lstrip("\ufeff")))

    if not reader.fieldnames:
        raise ValueError("CSV must contain a header row")

    headers = {
        name.strip().lower(): name
        for name in reader.fieldnames
        if name and name.strip()
    }

    def find_column(*names):
        for name in names:
            if name in headers:
                return headers[name]
        return None

    time_col = find_column(
        "time", "timestamp", "datetime", "date", "time_utc", "gmt time"
    )
    open_col = find_column("open", "o")
    high_col = find_column("high", "h")
    low_col = find_column("low", "l")
    close_col = find_column("close", "c")
    volume_col = find_column("volume", "vol", "tick_volume")

    missing = [
        name
        for name, col in (
            ("time/date", time_col),
            ("open", open_col),
            ("high", high_col),
            ("low", low_col),
            ("close", close_col),
        )
        if col is None
    ]

    if missing:
        raise ValueError(
            "Missing required CSV columns: " + ", ".join(missing)
        )

    rows = []

    for line_number, row in enumerate(reader, start=2):
        if not row or not any(str(v or "").strip() for v in row.values()):
            continue

        try:
            t = parse_timestamp(str(row[time_col]))
            o = float(row[open_col])
            h = float(row[high_col])
            l = float(row[low_col])
            c = float(row[close_col])

            if min(o, h, l, c) <= 0:
                raise ValueError("Prices must be positive")

            if h < max(o, c, l) or l > min(o, c, h):
                raise ValueError("Invalid OHLC values")

            candle = {
                "time": t,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 0,
            }

            if volume_col and row.get(volume_col):
                candle["volume"] = max(
                    0, int(float(row[volume_col]))
                )

            rows.append(candle)

        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(
                f"Invalid CSV row {line_number}: {exc}"
            ) from exc

    if len(rows) < 50:
        raise ValueError(
            f"Need at least 50 valid candles; found {len(rows)}"
        )

    rows.sort(key=lambda candle: candle["time"])

    for previous, current in zip(rows, rows[1:]):
        if previous["time"] == current["time"]:
            raise ValueError(
                "Duplicate timestamps found in the CSV"
            )

    return rows


def load_bundled_gold_data() -> None:
    """Load the committed XAUUSD M15 CSV whenever the API starts."""
    if not GOLD_CSV_PATH.is_file():
        print(f"Gold CSV not found: {GOLD_CSV_PATH}")
        return

    try:
        contents = GOLD_CSV_PATH.read_text(encoding="utf-8-sig")
        rows = normalize_csv(contents)

        uploaded_data["XAUUSD:15m"] = {
            "symbol": "XAUUSD",
            "timeframe": "15m",
            "source": "historical_csv",
            "candles": rows,
            "filename": GOLD_CSV_PATH.name,
        }

        print(
            f"Loaded XAUUSD M15 historical data: "
            f"{len(rows)} candles from {GOLD_CSV_PATH.name}"
        )

    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"Failed to load bundled gold CSV: {exc}")


@app.on_event("startup")
def startup_load_data():
    load_bundled_gold_data()


@app.get("/api/health")
def health():
    datasets = [
        {
            "key": key,
            "candles": len(dataset["candles"]),
            "source": dataset["source"],
        }
        for key, dataset in uploaded_data.items()
    ]

    return {
        "status": "ok",
        "app": "MarketForge API",
        "data_mode": (
            "historical_csv" if uploaded_data else "synthetic_demo"
        ),
        "uploaded_datasets": datasets,
        "bundled_gold_file_exists": GOLD_CSV_PATH.is_file(),
    }


@app.post("/api/upload-csv")
async def upload_csv(
    file: UploadFile = File(...),
    symbol: str = Query(
        default="XAUUSD", min_length=1, max_length=20
    ),
    timeframe: Timeframe = Query(default="15m"),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Please upload a .csv file")

    raw = await file.read(25 * 1024 * 1024 + 1)

    if len(raw) > 25 * 1024 * 1024:
        raise HTTPException(
            413, "CSV file must be 25 MB or smaller"
        )

    try:
        contents = raw.decode("utf-8-sig")
        rows = normalize_csv(contents)
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        await file.close()

    key = f"{symbol.upper()}:{timeframe}"

    uploaded_data[key] = {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "source": "historical_csv",
        "candles": rows,
        "filename": file.filename,
    }

    return {
        "status": "uploaded",
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "source": "historical_csv",
        "candles_loaded": len(rows),
        "first_timestamp": rows[0]["time"],
        "last_timestamp": rows[-1]["time"],
        "filename": file.filename,
    }


@app.get("/api/candles")
def candles(
    symbol: str = "XAUUSD",
    timeframe: Timeframe = "15m",
    limit: int = 500,
):
    if not 50 <= limit <= 3000:
        raise HTTPException(
            400, "limit must be between 50 and 3000"
        )

    key = f"{symbol.upper()}:{timeframe}"

    if key in uploaded_data:
        dataset = uploaded_data[key]
        return {
            **dataset,
            "candles": dataset["candles"][-limit:],
        }

    # Synthetic data is for chart previews only.
    step = STEP_MINUTES[timeframe]
    now = datetime.now(timezone.utc).replace(
        second=0, microsecond=0
    )
    base = 2350.0 if symbol.upper() == "XAUUSD" else 100.0
    rows = []
    price = base
    start = now - timedelta(minutes=step * limit)

    for i in range(limit):
        t = start + timedelta(minutes=step * i)
        trend = 0.025 * sin(i / 37) + 0.008 * cos(i / 13)
        change = (
            trend
            + 0.006 * sin(i * 1.71)
            + 0.004 * cos(i * 0.43)
        )

        o = price
        c = max(0.01, o * (1 + change / 100))
        wick = o * (
            0.0012 + abs(sin(i * 0.91)) * 0.001
        )
        h = max(o, c) + wick
        l = max(0.01, min(o, c) - wick * 0.85)

        rows.append({
            "time": int(t.timestamp()),
            "open": round(o, 4),
            "high": round(h, 4),
            "low": round(l, 4),
            "close": round(c, 4),
            "volume": int(
                100 + abs(sin(i * 0.4)) * 900
            ),
        })

        price = c

    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "source": "synthetic_demo",
        "candles": rows,
    }


@app.post("/api/backtest")
def backtest(req: BacktestRequest):
    if (
        req.strategy == "sma_crossover"
        and req.fast_period >= req.slow_period
    ):
        raise HTTPException(
            400, "fast_period must be smaller than slow_period"
        )

    if req.strategy == "fair_pricing_reversion" and (
        req.symbol.upper() != "XAUUSD"
        or req.timeframe != "15m"
    ):
        raise HTTPException(
            400,
            "Fair Pricing Reversion is currently enabled only "
            "for XAUUSD on 15m.",
        )

    key = f"{req.symbol.upper()}:{req.timeframe}"

    if key not in uploaded_data:
        raise HTTPException(
            400,
            "No historical CSV loaded for this symbol/timeframe. "
            "Ensure the CSV exists in backend/data and restart the API.",
        )

    dataset = uploaded_data[key]
    data = dataset["candles"]

    try:
        if req.strategy == "fair_pricing_reversion":
            result = run_fair_pricing_backtest(
                data,
                initial_balance=req.initial_balance,
                fee_bps=req.fee_bps,
                ema_period=req.ema_period,
                atr_period=req.atr_period,
                stretch_atr=req.stretch_atr,
                stop_atr=req.stop_atr,
                reward_risk=req.reward_risk,
                swing_lookback=req.swing_lookback,
            )
        else:
            result = run_sma_backtest(
                data,
                req.fast_period,
                req.slow_period,
                req.initial_balance,
                req.fee_bps,
            )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    result["strategy"] = req.strategy
    result["symbol"] = req.symbol.upper()
    result["timeframe"] = req.timeframe
    result["data_source"] = dataset["source"]
    result["candles_tested"] = len(data)

    return result
