from __future__ import annotations

from datetime import datetime
from math import isfinite
from zoneinfo import ZoneInfo


def sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)

    if period < 1:
        return out

    total = 0.0

    for i, value in enumerate(values):
        total += value

        if i >= period:
            total -= values[i - period]

        if i >= period - 1:
            out[i] = total / period

    return out


def ema(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)

    if period < 1 or len(values) < period:
        return out

    alpha = 2.0 / (period + 1.0)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    previous = seed

    for i in range(period, len(values)):
        previous = (
            alpha * values[i]
            + (1 - alpha) * previous
        )
        out[i] = previous

    return out


def atr(
    candles: list[dict],
    period: int = 14,
) -> list[float | None]:
    trs: list[float] = []

    for i, c in enumerate(candles):
        if i == 0:
            tr = float(c["high"]) - float(c["low"])
        else:
            prev_close = float(candles[i - 1]["close"])

            tr = max(
                float(c["high"]) - float(c["low"]),
                abs(float(c["high"]) - prev_close),
                abs(float(c["low"]) - prev_close),
            )

        trs.append(tr)

    return ema(trs, period)


def _max_drawdown(equity: list[float]) -> float:
    peak = equity[0] if equity else 0.0
    worst = 0.0

    for value in equity:
        peak = max(peak, value)

        if peak > 0:
            worst = max(
                worst,
                (peak - value) / peak * 100,
            )

    return worst


def _result(
    initial_balance: float,
    balance: float,
    trades: list[dict],
    equity_curve: list[dict],
    candles_tested: int,
    strategy_name: str,
    assumptions: list[str],
) -> dict:
    wins = sum(1 for t in trades if t["pnl"] > 0)

    return {
        "strategy": strategy_name,
        "initial_balance": round(initial_balance, 2),
        "final_balance": round(balance, 2),
        "net_return_pct": round(
            (balance / initial_balance - 1) * 100,
            3,
        ),
        "trades": len(trades),
        "win_rate_pct": (
            round(wins / len(trades) * 100, 2)
            if trades
            else 0.0
        ),
        "max_drawdown_pct": round(
            _max_drawdown(
                [p["equity"] for p in equity_curve]
            ),
            2,
        ),
        "candles_tested": candles_tested,
        "trade_list": trades[-100:],
        "equity_curve": equity_curve[-1000:],
        "assumptions": assumptions,
    }


def run_sma_backtest(
    candles: list[dict],
    fast_period: int,
    slow_period: int,
    initial_balance: float,
    fee_bps: float,
) -> dict:
    if fast_period >= slow_period:
        raise ValueError(
            "fast_period must be smaller than slow_period"
        )

    if len(candles) < slow_period + 3:
        raise ValueError(
            "Not enough candles for the selected SMA periods"
        )

    closes = [float(c["close"]) for c in candles]
    fast = sma(closes, fast_period)
    slow = sma(closes, slow_period)

    balance = float(initial_balance)
    position = None
    trades: list[dict] = []
    equity_curve = []
    fee_rate = fee_bps / 10000.0

    for i in range(1, len(candles) - 1):
        current_time = int(candles[i]["time"])

        if (
            position is not None
            and fast[i] is not None
            and slow[i] is not None
        ):
            if (
                fast[i - 1] is not None
                and slow[i - 1] is not None
                and fast[i - 1] >= slow[i - 1]
                and fast[i] < slow[i]
            ):
                exit_price = float(candles[i + 1]["open"])
                gross_pct = (
                    exit_price / position["entry"] - 1
                )
                exit_fee = balance * fee_rate
                pnl = (
                    balance * gross_pct
                    - position["entry_fee"]
                    - exit_fee
                )
                balance += pnl

                trades.append({
                    "entry_time": position["entry_time"],
                    "exit_time": int(candles[i + 1]["time"]),
                    "entry": round(position["entry"], 5),
                    "exit": round(exit_price, 5),
                    "pnl": round(pnl, 2),
                    "return_pct": round(
                        pnl / max(
                            position["balance_before"],
                            1e-9,
                        ) * 100,
                        3,
                    ),
                    "exit_reason": "SMA crossunder",
                })

                position = None

        if (
            position is None
            and fast[i - 1] is not None
            and slow[i - 1] is not None
            and fast[i] is not None
            and slow[i] is not None
        ):
            if (
                fast[i - 1] <= slow[i - 1]
                and fast[i] > slow[i]
            ):
                entry_price = float(candles[i + 1]["open"])
                entry_fee = balance * fee_rate
                balance -= entry_fee

                position = {
                    "entry": entry_price,
                    "entry_time": int(candles[i + 1]["time"]),
                    "entry_fee": entry_fee,
                    "balance_before": balance + entry_fee,
                }

        mark = balance

        if position is not None:
            mark += balance * (
                float(candles[i]["close"])
                / position["entry"] - 1
            )

        equity_curve.append({
            "time": current_time,
            "equity": round(mark, 2),
        })

    if position is not None:
        last = candles[-1]
        exit_price = float(last["close"])
        gross_pct = exit_price / position["entry"] - 1
        exit_fee = balance * fee_rate
        pnl = (
            balance * gross_pct
            - position["entry_fee"]
            - exit_fee
        )
        balance += pnl

        trades.append({
            "entry_time": position["entry_time"],
            "exit_time": int(last["time"]),
            "entry": round(position["entry"], 5),
            "exit": round(exit_price, 5),
            "pnl": round(pnl, 2),
            "return_pct": round(
                pnl / max(
                    position["balance_before"],
                    1e-9,
                ) * 100,
                3,
            ),
            "exit_reason": "End of data",
        })

    if (
        not equity_curve
        or equity_curve[-1]["equity"] != round(balance, 2)
    ):
        equity_curve.append({
            "time": int(candles[-1]["time"]),
            "equity": round(balance, 2),
        })

    return _result(
        initial_balance,
        balance,
        trades,
        equity_curve,
        len(candles),
        "sma_crossover",
        [
            "Long-only SMA crossover; entry/exit signals use "
            "closed candles and fill at the next candle open.",
            "Fee is approximated as fee_bps on each side; "
            "spread, slippage, financing and intrabar execution "
            "are not modeled.",
        ],
    )


def _ny_minutes(timestamp: int) -> int:
    dt = datetime.fromtimestamp(
        timestamp,
        tz=ZoneInfo("UTC"),
    ).astimezone(ZoneInfo("America/New_York"))

    return dt.hour * 60 + dt.minute


def _hourly_trend_filter(
    candles: list[dict],
    period: int = 50,
) -> list[float | None]:
    """Map each M15 candle to the EMA of the last fully completed hourly candle."""

    buckets: dict[int, dict] = {}

    for c in candles:
        hour = int(c["time"]) // 3600

        if hour not in buckets:
            buckets[hour] = {
                "time": hour * 3600,
                "open": float(c["open"]),
                "high": float(c["high"]),
                "low": float(c["low"]),
                "close": float(c["close"]),
            }
        else:
            b = buckets[hour]
            b["high"] = max(
                b["high"], float(c["high"])
            )
            b["low"] = min(
                b["low"], float(c["low"])
            )
            b["close"] = float(c["close"])

    hours = sorted(buckets)
    hourly = [buckets[h] for h in hours]

    hourly_ema = ema(
        [c["close"] for c in hourly],
        period,
    )

    by_hour = {
        h: hourly_ema[i - 1] if i > 0 else None
        for i, h in enumerate(hours)
    }

    return [
        by_hour.get(int(c["time"]) // 3600)
        for c in candles
    ]


def run_fair_pricing_backtest(
    candles: list[dict],
    initial_balance: float = 10000,
    fee_bps: float = 2,
    ema_period: int = 50,
    atr_period: int = 14,
    stretch_atr: float = 0.8,
    stop_atr: float = 1.5,
    reward_risk: float = 1.0,
    swing_lookback: int = 5,
) -> dict:
    if len(candles) < max(
        ema_period + 5,
        atr_period + swing_lookback + 5,
    ):
        raise ValueError(
            "Not enough M15 candles for Fair Pricing Reversion."
        )

    closes = [float(c["close"]) for c in candles]
    fair = ema(closes, ema_period)
    atr_values = atr(candles, atr_period)
    hourly_ema = _hourly_trend_filter(candles, 50)

    balance = float(initial_balance)
    fee_rate = fee_bps / 10000.0
    position = None
    trades: list[dict] = []
    equity_curve: list[dict] = []

    for i in range(1, len(candles)):
        c = candles[i]
        close = float(c["close"])
        high = float(c["high"])
        low = float(c["low"])
        timestamp = int(c["time"])

        if (
            fair[i] is None
            or atr_values[i] is None
            or hourly_ema[i] is None
        ):
            equity_curve.append({
                "time": timestamp,
                "equity": round(balance, 2),
            })
            continue

        session_minute = _ny_minutes(timestamp)
        in_session = (
            9 * 60 + 30
            <= session_minute
            < 12 * 60
        )

        if position:
            exit_price = None
            reason = None

            if position["side"] == "long":
                if low <= position["stop"]:
                    exit_price, reason = (
                        position["stop"], "Stop loss"
                    )
                elif high >= position["target"]:
                    exit_price, reason = (
                        position["target"], "Take profit"
                    )
                elif close >= position["fair_at_entry"]:
                    exit_price, reason = (
                        close, "Fair value reached"
                    )
            else:
                if high >= position["stop"]:
                    exit_price, reason = (
                        position["stop"], "Stop loss"
                    )
                elif low <= position["target"]:
                    exit_price, reason = (
                        position["target"], "Take profit"
                    )
                elif close <= position["fair_at_entry"]:
                    exit_price, reason = (
                        close, "Fair value reached"
                    )

            if exit_price is not None:
                direction = (
                    1 if position["side"] == "long" else -1
                )
                qty = position["qty"]

                gross = (
                    (exit_price - position["entry"])
                    * qty
                    * direction
                )

                fee_cost = (
                    abs(position["entry"] * qty)
                    + abs(exit_price * qty)
                ) * fee_rate

                pnl = gross - fee_cost
                balance += pnl

                trades.append({
                    "entry_time": position["entry_time"],
                    "exit_time": timestamp,
                    "entry": round(position["entry"], 5),
                    "exit": round(exit_price, 5),
                    "pnl": round(pnl, 2),
                    "return_pct": round(
                        pnl / max(
                            position["risk_balance"],
                            1e-9,
                        ) * 100,
                        3,
                    ),
                    "exit_reason": reason,
                    "side": position["side"],
                })

                position = None

        if (
            position is None
            and in_session
            and i >= swing_lookback
            and balance > 0
        ):
            fair_value = float(fair[i])
            av = float(atr_values[i])
            trend = float(hourly_ema[i])
            prev_close = float(candles[i - 1]["close"])
            prev_fair = fair[i - 1]

            bullish = close > float(c["open"])
            bearish = close < float(c["open"])

            long_setup = (
                prev_fair is not None
                and close < fair_value - stretch_atr * av
                and bullish
                and close > prev_close
                and close > trend
            )

            short_setup = (
                prev_fair is not None
                and close > fair_value + stretch_atr * av
                and bearish
                and close < prev_close
                and close < trend
            )

            if long_setup or short_setup:
                side = "long" if long_setup else "short"

                entry = (
                    float(candles[i + 1]["open"])
                    if i + 1 < len(candles)
                    else close
                )

                swing_lows = [
                    float(x["low"])
                    for x in candles[
                        max(0, i - swing_lookback + 1):i + 1
                    ]
                ]

                swing_highs = [
                    float(x["high"])
                    for x in candles[
                        max(0, i - swing_lookback + 1):i + 1
                    ]
                ]

                if side == "long":
                    stop = min(swing_lows)

                    if entry - stop < 0.1 * av:
                        stop = entry - stop_atr * av

                    risk = entry - stop
                    target = entry + risk * reward_risk
                else:
                    stop = max(swing_highs)

                    if stop - entry < 0.1 * av:
                        stop = entry + stop_atr * av

                    risk = stop - entry
                    target = entry - risk * reward_risk

                if (
                    risk > 0
                    and all(
                        isfinite(x)
                        for x in (entry, stop, target)
                    )
                ):
                    risk_balance = balance
                    risk_cash = risk_balance * 0.005
                    qty = risk_cash / risk
                    entry_fee = abs(entry * qty) * fee_rate
                    balance -= entry_fee

                    position = {
                        "side": side,
                        "entry": entry,
                        "stop": stop,
                        "target": target,
                        "qty": qty,
                        "entry_time": (
                            int(candles[i + 1]["time"])
                            if i + 1 < len(candles)
                            else timestamp
                        ),
                        "fair_at_entry": fair_value,
                        "risk_balance": risk_balance,
                    }

        mark = balance

        if position:
            direction = (
                1 if position["side"] == "long" else -1
            )

            mark += (
                (close - position["entry"])
                * position["qty"]
                * direction
            )

        equity_curve.append({
            "time": timestamp,
            "equity": round(mark, 2),
        })

    if position:
        last = candles[-1]
        exit_price = float(last["close"])
        direction = (
            1 if position["side"] == "long" else -1
        )

        gross = (
            (exit_price - position["entry"])
            * position["qty"]
            * direction
        )

        fee_cost = abs(
            exit_price * position["qty"]
        ) * fee_rate

        pnl = gross - fee_cost
        balance += pnl

        trades.append({
            "entry_time": position["entry_time"],
            "exit_time": int(last["time"]),
            "entry": round(position["entry"], 5),
            "exit": round(exit_price, 5),
            "pnl": round(pnl, 2),
            "return_pct": round(
                pnl / max(
                    position["risk_balance"],
                    1e-9,
                ) * 100,
                3,
            ),
            "exit_reason": "End of data",
            "side": position["side"],
        })

        equity_curve.append({
            "time": int(last["time"]),
            "equity": round(balance, 2),
        })

    return _result(
        initial_balance,
        balance,
        trades,
        equity_curve,
        len(candles),
        "fair_pricing_reversion",
        [
            "Experimental Fair Pricing Reversion rules: EMA fair value, ATR stretch, bullish/bearish reversal candle, and completed-hour EMA trend filter.",
            "Entries are modeled at the next M15 candle open; session filter is 09:30–12:00 America/New_York, including daylight-saving changes.",
            "Position size targets 0.5% of balance at the stop distance; this is a simplified price-unit model, not broker-specific XAUUSD contract sizing.",
            "If both stop and target are touched in the same candle, stop loss is assumed first. Spread, slippage, financing, gaps and broker-specific tick value are not fully modeled.",
            "This is an experimental backtest implementation and is not evidence of future profitability.",
        ],
    )
