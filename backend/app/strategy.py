
from typing import Any


def sma(values: list[float], period: int) -> list[float | None]:
    out = [None] * len(values)
    running = 0.0

    for i, value in enumerate(values):
        running += value
        if i >= period:
            running -= values[i - period]
        if i >= period - 1:
            out[i] = running / period

    return out


def run_sma_backtest(
    candles: list[dict[str, Any]],
    fast_period: int,
    slow_period: int,
    initial_balance: float,
    fee_bps: float,
):
    closes = [float(c["close"]) for c in candles]
    fast = sma(closes, fast_period)
    slow = sma(closes, slow_period)

    balance = float(initial_balance)
    fee = fee_bps / 10000.0
    position = None
    trades = []
    equity = []

    def mark_equity(price):
        if position is None:
            return balance

        return (
            position["capital"] * (1 - fee)
            * (price / position["entry"]) * (1 - fee)
        )

    for i in range(len(candles) - 1):
        if i > 0 and fast[i] is not None and slow[i] is not None:
            if fast[i - 1] is not None and slow[i - 1] is not None:
                crossed_up = (
                    fast[i - 1] <= slow[i - 1]
                    and fast[i] > slow[i]
                )
                crossed_down = (
                    fast[i - 1] >= slow[i - 1]
                    and fast[i] < slow[i]
                )

                fill = float(candles[i + 1]["open"])

                if position is None and crossed_up:
                    position = {
                        "entry": fill,
                        "entry_time": int(candles[i + 1]["time"]),
                        "entry_index": i + 1,
                        "capital": balance,
                    }

                elif position is not None and crossed_down:
                    capital = position["capital"]
                    final_balance = (
                        capital * (1 - fee)
                        * (fill / position["entry"]) * (1 - fee)
                    )
                    pnl = final_balance - capital

                    trades.append({
                        "entry_time": position["entry_time"],
                        "exit_time": int(candles[i + 1]["time"]),
                        "entry": round(position["entry"], 4),
                        "exit": round(fill, 4),
                        "return_pct": round(pnl / capital * 100, 3),
                        "pnl": round(pnl, 2),
                        "exit_reason": "SMA crossunder",
                        "bars_held": i + 1 - position["entry_index"],
                    })

                    balance = final_balance
                    position = None

        candle = candles[i + 1]
        current_equity = mark_equity(float(candle["close"]))

        equity.append({
            "time": int(candle["time"]),
            "equity": round(current_equity, 2),
        })

    if position is not None and candles:
        final_candle = candles[-1]
        final_price = float(final_candle["close"])
        capital = position["capital"]

        balance = (
            capital * (1 - fee)
            * (final_price / position["entry"]) * (1 - fee)
        )
        pnl = balance - capital

        trades.append({
            "entry_time": position["entry_time"],
            "exit_time": int(final_candle["time"]),
            "entry": round(position["entry"], 4),
            "exit": round(final_price, 4),
            "return_pct": round(pnl / capital * 100, 3),
            "pnl": round(pnl, 2),
            "exit_reason": "End of sample",
            "bars_held": len(candles) - 1 - position["entry_index"],
        })

        if equity:
            equity[-1]["equity"] = round(balance, 2)

    peak = float(initial_balance)
    max_drawdown = 0.0

    for point in equity:
        value = point["equity"]
        peak = max(peak, value)

        if peak > 0:
            drawdown = (peak - value) / peak * 100
            max_drawdown = max(max_drawdown, drawdown)

    wins = sum(1 for trade in trades if trade["pnl"] > 0)

    return {
        "symbol": "demo",
        "initial_balance": round(initial_balance, 2),
        "final_balance": round(balance, 2),
        "net_return_pct": round(
            (balance / initial_balance - 1) * 100, 3
        ) if initial_balance else 0.0,
        "trades": len(trades),
        "win_rate_pct": round(
            wins / len(trades) * 100, 2
        ) if trades else 0.0,
        "max_drawdown_pct": round(max_drawdown, 2),
        "fee_bps_per_side": fee_bps,
        "assumptions": [
            "Synthetic demo candles only; not market data.",
            "Long-only SMA crossover; no short positions.",
            "Signals use completed candles and fill at next candle open.",
            "Entry and exit fees are modeled.",
            "Spread, slippage, financing and intrabar stops are not modeled.",
            "Open positions are marked to market for drawdown estimation.",
        ],
        "trade_list": trades[-100:],
        "equity_curve": equity[-1000:],
    }
