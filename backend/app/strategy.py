from __future__ import annotations

from datetime import datetime
from math import isfinite
from zoneinfo import ZoneInfo


# ============================================================
# Indicators
# ============================================================

def sma(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)

    if period < 1:
        return result

    total = 0.0

    for i, value in enumerate(values):
        total += value

        if i >= period:
            total -= values[i - period]

        if i >= period - 1:
            result[i] = total / period

    return result


def ema(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)

    if period < 1 or len(values) < period:
        return result

    alpha = 2.0 / (period + 1.0)
    previous = sum(values[:period]) / period
    result[period - 1] = previous

    for i in range(period, len(values)):
        previous = (
            alpha * values[i]
            + (1.0 - alpha) * previous
        )
        result[i] = previous

    return result


def atr(
    candles: list[dict],
    period: int = 14,
) -> list[float | None]:
    true_ranges: list[float] = []

    for i, candle in enumerate(candles):
        high = float(candle["high"])
        low = float(candle["low"])

        if i == 0:
            true_range = high - low
        else:
            previous_close = float(candles[i - 1]["close"])

            true_range = max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            )

        true_ranges.append(true_range)

    return ema(true_ranges, period)


# ============================================================
# Shared calculations
# ============================================================

def _max_drawdown(equity: list[float]) -> float:
    if not equity:
        return 0.0

    peak = equity[0]
    worst = 0.0

    for value in equity:
        peak = max(peak, value)

        if peak > 0:
            drawdown = (peak - value) / peak * 100.0
            worst = max(worst, drawdown)

    return worst


def _result(
    initial_balance: float,
    final_balance: float,
    trades: list[dict],
    equity_curve: list[dict],
    candles_tested: int,
    strategy_name: str,
    assumptions: list[str],
) -> dict:
    wins = sum(1 for trade in trades if trade["pnl"] > 0)

    equity_values = [
        float(point["equity"])
        for point in equity_curve
    ]

    return {
        "strategy": strategy_name,
        "initial_balance": round(initial_balance, 2),
        "final_balance": round(final_balance, 2),
        "net_return_pct": round(
            (final_balance / initial_balance - 1.0) * 100.0,
            3,
        ),
        "trades": len(trades),
        "win_rate_pct": round(
            wins / len(trades) * 100.0,
            2,
        ) if trades else 0.0,
        "max_drawdown_pct": round(
            _max_drawdown(equity_values),
            2,
        ),
        "candles_tested": candles_tested,
        "trade_list": trades[-100:],
        "equity_curve": equity_curve[-1000:],
        "assumptions": assumptions,
    }


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
    """
    Build hourly candles from M15 data.

    Each M15 candle receives the EMA from the previous completed
    hourly candle, avoiding use of the current unfinished hour.
    """

    buckets: dict[int, dict] = {}

    for candle in candles:
        hour = int(candle["time"]) // 3600

        if hour not in buckets:
            buckets[hour] = {
                "time": hour * 3600,
                "open": float(candle["open"]),
                "high": float(candle["high"]),
                "low": float(candle["low"]),
                "close": float(candle["close"]),
            }
        else:
            bucket = buckets[hour]
            bucket["high"] = max(
                bucket["high"],
                float(candle["high"]),
            )
            bucket["low"] = min(
                bucket["low"],
                float(candle["low"]),
            )
            bucket["close"] = float(candle["close"])

    hours = sorted(buckets)
    hourly_candles = [buckets[hour] for hour in hours]

    hourly_ema = ema(
        [candle["close"] for candle in hourly_candles],
        period,
    )

    previous_completed_ema = {}

    for i, hour in enumerate(hours):
        previous_completed_ema[hour] = (
            hourly_ema[i - 1] if i > 0 else None
        )

    return [
        previous_completed_ema.get(int(candle["time"]) // 3600)
        for candle in candles
    ]


# ============================================================
# SMA Crossover
# ============================================================

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

    closes = [float(candle["close"]) for candle in candles]
    fast = sma(closes, fast_period)
    slow = sma(closes, slow_period)

    balance = float(initial_balance)
    fee_rate = fee_bps / 10000.0

    position = None
    pending_entry = False
    pending_exit = False

    trades: list[dict] = []
    equity_curve: list[dict] = []

    for i, candle in enumerate(candles):
        timestamp = int(candle["time"])
        open_price = float(candle["open"])
        close_price = float(candle["close"])

        # Execute an entry signal from the previous candle
        # at this candle's open.
        if pending_entry and position is None and balance > 0:
            entry = open_price
            balance_before = balance

            # Long-only model using available balance.
            quantity = balance_before / (
                entry * (1.0 + fee_rate)
            )

            entry_fee = abs(entry * quantity) * fee_rate
            balance -= entry_fee

            position = {
                "entry": entry,
                "entry_time": timestamp,
                "quantity": quantity,
                "entry_fee": entry_fee,
                "balance_before": balance_before,
            }

            pending_entry = False

        # Execute an exit signal from the previous candle
        # at this candle's open.
        if pending_exit and position is not None:
            exit_price = open_price
            quantity = position["quantity"]

            gross_pnl = (
                exit_price - position["entry"]
            ) * quantity

            exit_fee = abs(exit_price * quantity) * fee_rate

            # Entry fee was already deducted at entry.
            balance += gross_pnl - exit_fee

            total_pnl = (
                gross_pnl
                - position["entry_fee"]
                - exit_fee
            )

            trades.append({
                "entry_time": position["entry_time"],
                "exit_time": timestamp,
                "entry": round(position["entry"], 5),
                "exit": round(exit_price, 5),
                "pnl": round(total_pnl, 2),
                "return_pct": round(
                    total_pnl
                    / max(position["balance_before"], 1e-9)
                    * 100.0,
                    3,
                ),
                "exit_reason": "SMA crossunder",
                "side": "long",
            })

            position = None
            pending_exit = False

        # Signals use the candle that has just closed.
        if i > 0 and fast[i] is not None and slow[i] is not None:
            previous_fast = fast[i - 1]
            previous_slow = slow[i - 1]

            if previous_fast is not None and previous_slow is not None:
                crossed_up = (
                    previous_fast <= previous_slow
                    and fast[i] > slow[i]
                )

                crossed_down = (
                    previous_fast >= previous_slow
                    and fast[i] < slow[i]
                )

                if position is None and crossed_up:
                    pending_entry = True
                    pending_exit = False

                elif position is not None and crossed_down:
                    pending_exit = True

        marked_equity = balance

        if position is not None:
            marked_equity += (
                close_price - position["entry"]
            ) * position["quantity"]

        equity_curve.append({
            "time": timestamp,
            "equity": round(marked_equity, 2),
        })

    # Close any open position at the final available close.
    if position is not None:
        last = candles[-1]
        exit_price = float(last["close"])
        quantity = position["quantity"]

        gross_pnl = (
            exit_price - position["entry"]
        ) * quantity

        exit_fee = abs(exit_price * quantity) * fee_rate
        balance += gross_pnl - exit_fee

        total_pnl = (
            gross_pnl
            - position["entry_fee"]
            - exit_fee
        )

        trades.append({
            "entry_time": position["entry_time"],
            "exit_time": int(last["time"]),
            "entry": round(position["entry"], 5),
            "exit": round(exit_price, 5),
            "pnl": round(total_pnl, 2),
            "return_pct": round(
                total_pnl
                / max(position["balance_before"], 1e-9)
                * 100.0,
                3,
            ),
            "exit_reason": "End of data",
            "side": "long",
        })

        if equity_curve:
            equity_curve[-1]["equity"] = round(balance, 2)

    return _result(
        initial_balance,
        balance,
        trades,
        equity_curve,
        len(candles),
        "sma_crossover",
        [
            "Long-only SMA crossover. Signals use closed candles "
            "and execute at the next candle open.",
            "Entry and exit fees are each charged once.",
            "Spread, slippage, financing and broker-specific "
            "contract sizing are not modeled.",
        ],
    )


# ============================================================
# Fair Pricing Reversion
# ============================================================

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

    closes = [float(candle["close"]) for candle in candles]
    fair_values = ema(closes, ema_period)
    atr_values = atr(candles, atr_period)
    hourly_ema = _hourly_trend_filter(candles, 50)

    balance = float(initial_balance)
    fee_rate = fee_bps / 10000.0

    position = None
    pending_signal = None

    trades: list[dict] = []
    equity_curve: list[dict] = []

    for i, candle in enumerate(candles):
        timestamp = int(candle["time"])
        open_price = float(candle["open"])
        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])

        # ----------------------------------------------------
        # Execute pending signal at the current candle's open.
        # ----------------------------------------------------
        if pending_signal is not None and position is None:
            side = pending_signal["side"]
            stop = pending_signal["stop"]
            target = pending_signal["target"]
            fair_at_entry = pending_signal["fair"]

            entry = open_price

            # If the market gaps through the intended stop,
            # skip this entry rather than creating an invalid trade.
            if side == "long" and entry <= stop:
                pending_signal = None
            elif side == "short" and entry >= stop:
                pending_signal = None
            else:
                risk_distance = (
                    entry - stop
                    if side == "long"
                    else stop - entry
                )

                if risk_distance > 0 and balance > 0:
                    balance_before = balance

                    # Target 0.5% of balance at the stop distance.
                    risk_cash = balance_before * 0.005
                    quantity = risk_cash / risk_distance

                    entry_fee = abs(entry * quantity) * fee_rate

                    position = {
                        "side": side,
                        "entry": entry,
                        "stop": stop,
                        "target": target,
                        "quantity": quantity,
                        "entry_fee": entry_fee,
                        "entry_time": timestamp,
                        "balance_before": balance_before,
                        "fair_at_entry": fair_at_entry,
                    }

                    # Charge entry fee once, at entry.
                    balance -= entry_fee

                pending_signal = None

        # ----------------------------------------------------
        # Manage an open position using current candle prices.
        # If stop and target both hit, assume stop first.
        # ----------------------------------------------------
        if position is not None:
            exit_price = None
            exit_reason = None

            if position["side"] == "long":
                if low <= position["stop"]:
                    exit_price = position["stop"]
                    exit_reason = "Stop loss"
                elif high >= position["target"]:
                    exit_price = position["target"]
                    exit_reason = "Take profit"
                elif close >= position["fair_at_entry"]:
                    exit_price = close
                    exit_reason = "Fair value reached"

            else:
                if high >= position["stop"]:
                    exit_price = position["stop"]
                    exit_reason = "Stop loss"
                elif low <= position["target"]:
                    exit_price = position["target"]
                    exit_reason = "Take profit"
                elif close <= position["fair_at_entry"]:
                    exit_price = close
                    exit_reason = "Fair value reached"

            if exit_price is not None:
                quantity = position["quantity"]
                direction = (
                    1.0 if position["side"] == "long" else -1.0
                )

                gross_pnl = (
                    (exit_price - position["entry"])
                    * quantity
                    * direction
                )

                exit_fee = abs(exit_price * quantity) * fee_rate

                # Entry fee was already deducted at entry.
                balance += gross_pnl - exit_fee

                total_pnl = (
                    gross_pnl
                    - position["entry_fee"]
                    - exit_fee
                )

                trades.append({
                    "entry_time": position["entry_time"],
                    "exit_time": timestamp,
                    "entry": round(position["entry"], 5),
                    "exit": round(exit_price, 5),
                    "pnl": round(total_pnl, 2),
                    "return_pct": round(
                        total_pnl
                        / max(position["balance_before"], 1e-9)
                        * 100.0,
                        3,
                    ),
                    "exit_reason": exit_reason,
                    "side": position["side"],
                })

                position = None

        # ----------------------------------------------------
        # Generate a new signal only after this candle closes.
        # Entry will happen at the next candle's open.
        # ----------------------------------------------------
        if (
            position is None
            and pending_signal is None
            and i < len(candles) - 1
            and i >= swing_lookback
            and fair_values[i] is not None
            and fair_values[i - 1] is not None
            and atr_values[i] is not None
            and hourly_ema[i] is not None
            and balance > 0
        ):
            session_minute = _ny_minutes(timestamp)

            in_session = (
                9 * 60 + 30
                <= session_minute
                < 12 * 60
            )

            if in_session:
                fair = float(fair_values[i])
                av = float(atr_values[i])
                trend = float(hourly_ema[i])

                previous_close = float(candles[i - 1]["close"])

                bullish = close > open_price
                bearish = close < open_price

                # Reversion setup with hourly trend filter.
                long_setup = (
                    close < fair - stretch_atr * av
                    and bullish
                    and close > previous_close
                    and close > trend
                )

                short_setup = (
                    close > fair + stretch_atr * av
                    and bearish
                    and close < previous_close
                    and close < trend
                )

                if long_setup or short_setup:
                    side = "long" if long_setup else "short"

                    swing_start = max(
                        0, i - swing_lookback + 1
                    )
                    swing_candles = candles[swing_start:i + 1]

                    swing_low = min(
                        float(x["low"]) for x in swing_candles
                    )
                    swing_high = max(
                        float(x["high"]) for x in swing_candles
                    )

                    if side == "long":
                        stop = swing_low

                        if close - stop < 0.1 * av:
                            stop = close - stop_atr * av

                        risk_distance = close - stop
                        target = close + risk_distance * reward_risk

                    else:
                        stop = swing_high

                        if stop - close < 0.1 * av:
                            stop = close + stop_atr * av

                        risk_distance = stop - close
                        target = close - risk_distance * reward_risk

                    if (
                        risk_distance > 0
                        and all(
                            isfinite(value)
                            for value in (fair, av, stop, target)
                        )
                    ):
                        pending_signal = {
                            "side": side,
                            "stop": stop,
                            "target": target,
                            "fair": fair,
                        }

        # Mark equity using the closing price.
        marked_equity = balance

        if position is not None:
            direction = (
                1.0 if position["side"] == "long" else -1.0
            )

            marked_equity += (
                (close - position["entry"])
                * position["quantity"]
                * direction
            )

        equity_curve.append({
            "time": timestamp,
            "equity": round(marked_equity, 2),
        })

    # Close any remaining position at the final candle close.
    if position is not None:
        last = candles[-1]
        exit_price = float(last["close"])
        quantity = position["quantity"]

        direction = (
            1.0 if position["side"] == "long" else -1.0
        )

        gross_pnl = (
            (exit_price - position["entry"])
            * quantity
            * direction
        )

        exit_fee = abs(exit_price * quantity) * fee_rate
        balance += gross_pnl - exit_fee

        total_pnl = (
            gross_pnl
            - position["entry_fee"]
            - exit_fee
        )

        trades.append({
            "entry_time": position["entry_time"],
            "exit_time": int(last["time"]),
            "entry": round(position["entry"], 5),
            "exit": round(exit_price, 5),
            "pnl": round(total_pnl, 2),
            "return_pct": round(
                total_pnl
                / max(position["balance_before"], 1e-9)
                * 100.0,
                3,
            ),
            "exit_reason": "End of data",
            "side": position["side"],
        })

        if equity_curve:
            equity_curve[-1]["equity"] = round(balance, 2)

    return _result(
        initial_balance,
        balance,
        trades,
        equity_curve,
        len(candles),
        "fair_pricing_reversion",
        [
            "Experimental strategy: EMA fair value, ATR stretch, "
            "reversal candle, and previous completed hourly EMA filter.",
            "Signals are generated at candle close and entries execute "
            "at the next candle open.",
            "Session filter: 09:30–12:00 America/New_York, including "
            "daylight-saving changes.",
            "Position sizing targets 0.5% of balance at the stop "
            "distance using simplified price units.",
            "If stop and target are both touched within one candle, "
            "stop loss is assumed first.",
            "Entry and exit fees are each charged once. Spread, slippage, "
            "financing, gaps and broker-specific contract sizing are "
            "not fully modeled.",
            "Historical results are simulations and do not guarantee "
            "future profitability.",
        ],
    )
