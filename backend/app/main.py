
from datetime import datetime, timedelta, timezone
from math import sin, cos
from pathlib import Path
import csv
import io
import os
import re
from typing import Literal

from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .strategy import run_sma_backtest


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
    "1m": 1, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "4h": 240, "1d": 1440,
}

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Data is loaded from the repository's data directory at startup.
# Runtime uploads are held in memory until the service restarts.
uploaded_data: dict[str, dict] = {}


class BacktestRequest(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: Timeframe = "15m"
    fast_period: int = Field(default=9, ge=2, le=200)
    slow_period: int = Field(default=21, ge=3, le=500)
    initial_balance: float = Field(default=10000, gt=0)
    fee_bps: float = Field(default=2, ge=0, le=100)


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
    # Support comma-separated and semicolon-separated CSV files.
    sample = contents.lstrip("\ufeff")[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(contents.lstrip("\ufeff")), dialect=dialect)
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
        "time", "timestamp", "datetime", "date", "time_utc", "gmt time",
        "time (utc)", "gmt",
    )
    open_col = find_column("open", "o")
    high_col = find_column("high", "h")
    low_col = find_column("low", "l")
    close_col = find_column("close", "c")
    volume_col = find_column("volume", "vol", "tick_volume")

    missing = [
        name for name, col in (
            ("time/date", time_col), ("open", open_col),
            ("high", high_col), ("low", low_col), ("close", close_col),
        ) if col is None
    ]
    if missing:
        raise ValueError("Missing required CSV columns: " + ", ".join(missing))

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

            volume = 0
            if volume_col and row.get(volume_col):
                volume = max(0, int(float(row[volume_col])))

            rows.append({
                "time": t, "open": o, "high": h,
                "low": l, "close": c, "volume": volume,
            })
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(f"Invalid CSV row {line_number}: {exc}") from exc

    if len(rows) < 50:
        raise ValueError(f"Need at least 50 valid candles; found {len(rows)}")

    # Sort and de-duplicate timestamps.
    by_time = {row["time"]: row for row in rows}
    return [by_time[t] for t in sorted(by_time)]


def infer_timeframe(filename: str):
    name = filename.lower()
    patterns = (
        (r"(?<![a-z0-9])1m(?![a-z0-9])", "1m"),
        (r"(?<![a-z0-9])5m(?![a-z0-9])", "5m"),
        (r"(?<![a-z0-9])15m(?![a-z0-9])", "15m"),
        (r"(?<![a-z0-9])30m(?![a-z0-9])", "30m"),
        (r"(?<![a-z0-9])1h(?![a-z0-9])", "1h"),
        (r"(?<![a-z0-9])4h(?![a-z0-9])", "4h"),
        (r"(?<![a-z0-9])1d(?![a-z0-9])", "1d"),
    )
    for pattern, timeframe in patterns:
        if re.search(pattern, name):
            return timeframe
    return None


def load_repository_data():
    """Load CSVs bundled in backend/data on every API startup."""
    if not DATA_DIR.exists():
        return

    combined = {}

    for path in sorted(DATA_DIR.glob("*.csv")):
        timeframe = infer_timeframe(path.stem)
        if timeframe is None:
            print(f"Skipping {path.name}: timeframe not identified in filename")
            continue

        try:
            rows = normalize_csv(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, ValueError) as exc:
            print(f"Skipping {path.name}: {exc}")
            continue

        symbol = "XAUUSD" if "xau" in path.stem.lower() or "gold" in path.stem.lower() else None
        if symbol is None:
            print(f"Skipping {path.name}: symbol not identified in filename")
            continue

        key = f"{symbol}:{timeframe}"
        combined.setdefault(key, {})
        # When multiple files overlap, the later filename in sorted order wins
        # for duplicate timestamps. Prefer files with non-overlapping periods.
        for row in rows:
            combined[key][row["time"]] = row

    for key, candles_by_time in combined.items():
        rows = [candles_by_time[t] for t in sorted(candles_by_time)]
        if len(rows) < 50:
            continue
        symbol, timeframe = key.split(":", 1)
        uploaded_data[key] = {
            "symbol": symbol,
            "timeframe": timeframe,
            "source": "repository_csv",
            "candles": rows,
            "filename": "repository data",
        }
        print(f"Loaded {key}: {len(rows)} candles from {DATA_DIR}")


@app.on_event("startup")
def startup_load_data():
    load_repository_data()


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "app": "MarketForge API",
        "data_mode": "historical_csv" if uploaded_data else "synthetic_demo",
        "uploaded_datasets": [
            {
                "key": key,
                "candles": len(dataset["candles"]),
                "first_timestamp": dataset["candles"][0]["time"],
                "last_timestamp": dataset["candles"][-1]["time"],
                "source": dataset["source"],
            }
            for key, dataset in uploaded_data.items()
        ],
    }


@app.post("/api/upload-csv")
async def upload_csv(
    file: UploadFile = File(...),
    symbol: str = Query(default="XAUUSD", min_length=1, max_length=20),
    timeframe: Timeframe = Query(default="15m"),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Please upload a .csv file")

    raw = await file.read(25 * 1024 * 1024 + 1)
    if len(raw) > 25 * 1024 * 1024:
        raise HTTPException(413, "CSV file must be 25 MB or smaller")

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
        "source": "runtime_upload",
        "candles": rows,
        "filename": file.filename,
    }

    return {
        "status": "uploaded",
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "source": "runtime_upload",
        "candles_loaded": len(rows),
        "first_timestamp": rows[0]["time"],
        "last_timestamp": rows[-1]["time"],
        "filename": file.filename,
        "note": "Runtime uploads are temporary. Add permanent datasets to backend/data.",
    }


@app.get("/api/candles")
def candles(
    symbol: str = "XAUUSD",
    timeframe: Timeframe = "15m",
    limit: int = 500,
):
    if not 50 <= limit <= 3000:
        raise HTTPException(400, "limit must be between 50 and 3000")

    key = f"{symbol.upper()}:{timeframe}"
    if key in uploaded_data:
        dataset = uploaded_data[key]
        return {
            **dataset,
            "candles": dataset["candles"][-limit:],
        }

    # Demo candles are only for preview; backtests never use these.
    step = STEP_MINUTES[timeframe]
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    price = 2350.0 if symbol.upper() == "XAUUSD" else 100.0
    rows = []
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
            "volume": int(100 + abs(sin(i * 0.4)) * 900),
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
    if req.fast_period >= req.slow_period:
        raise HTTPException(400, "fast_period must be smaller than slow_period")

    key = f"{req.symbol.upper()}:{req.timeframe}"
    if key not in uploaded_data:
        raise HTTPException(
            400,
            f"No historical CSV found for {key}. "
            "Add a matching CSV to backend/data and redeploy.",
        )

    dataset = uploaded_data[key]
    data = dataset["candles"]

    result = run_sma_backtest(
        data,
        req.fast_period,
        req.slow_period,
        req.initial_balance,
        req.fee_bps,
    )
    result["symbol"] = req.symbol.upper()
    result["timeframe"] = req.timeframe
    result["data_source"] = dataset["source"]
    result["candles_tested"] = len(data)
    result["first_timestamp"] = data[0]["time"]
    result["last_timestamp"] = data[-1]["time"]
    return result
