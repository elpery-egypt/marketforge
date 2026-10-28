from typing import Any

def sma(values: list[float], period: int) -> list[float | None]:
    out = [None] * len(values)
    running = 0.0
    for i, value in enumerate(values):
        running += value
        if i >= period:
            running -= values[i-period]
        if i >= period - 1:
            out[i] = running / period
    return out

def run_sma_backtest(candles: list[dict[str, Any]], fast_period: int,
                     slow_period: int, initial_balance: float, fee_bps: float):
    closes = [float(c["close"]) for c in candles]
    fast = sma(closes, fast_period)
    slow = sma(closes, slow_period)
    balance = initial_balance
    position = None
    trades = []
    equity = []
    fee_rate = fee_bps / 10000.0

    # Signals are generated from completed candles and filled at next candle open
    # to avoid the most obvious same-close look-ahead bias.
    for i in range(1, len(candles) - 1):
        if fast[i] is None or slow[i] is None or fast[i-1] is None or slow[i-1] is None:
            equity.append({"time": candles[i]["time"], "equity": round(balance, 2)})
            continue
        crossed_up = fast[i-1] <= slow[i-1] and fast[i] > slow[i]
        crossed_down = fast[i-1] >= slow[i-1] and fast[i] < slow[i]
        fill_price = float(candles[i+1]["open"])

        if position is None and crossed_up:
            position = {"entry": fill_price, "time": candles[i+1]["time"]}
            balance *= (1 - fee_rate)
        elif position is not None and crossed_down:
            gross_return = fill_price / position["entry"] - 1
            net_return = gross_return - fee_rate
            pnl = balance * net_return
            balance += pnl
            trades.append({
                "entry_time": position["time"], "exit_time": candles[i+1]["time"],
                "entry": round(position["entry"], 4), "exit": round(fill_price, 4),
                "return_pct": round(net_return * 100, 3), "pnl": round(pnl, 2)
            })
            position = None
        equity.append({"time": candles[i]["time"], "equity": round(balance, 2)})

    if position is not None:
        final_price = float(candles[-1]["close"])
        gross_return = final_price / position["entry"] - 1
        net_return = gross_return - fee_rate
        pnl = balance * net_return
        balance += pnl
        trades.append({
            "entry_time": position["time"], "exit_time": candles[-1]["time"],
            "entry": round(position["entry"], 4), "exit": round(final_price, 4),
            "return_pct": round(net_return * 100, 3), "pnl": round(pnl, 2),
            "note": "Closed at end of sample"
        })

    wins = sum(1 for t in trades if t["pnl"] > 0)
    total_return = (balance / initial_balance - 1) * 100
    peak = initial_balance
    max_dd = 0.0
    for point in equity:
        peak = max(peak, point["equity"])
        if peak:
            max_dd = max(max_dd, (peak - point["equity"]) / peak * 100)
    return {
        "symbol": "demo",
        "initial_balance": round(initial_balance, 2),
        "final_balance": round(balance, 2),
        "net_return_pct": round(total_return, 3),
        "trades": len(trades),
        "win_rate_pct": round((wins / len(trades) * 100) if trades else 0, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "fee_bps_per_side": fee_bps,
        "assumptions": [
            "Synthetic demo candles only; not market data.",
            "Long-only SMA crossover; no short positions.",
            "Signals on close, fill on next candle open.",
            "Fees approximated; spread, slippage, financing and intrabar stops are not modeled."
        ],
        "trade_list": trades[-100:],
        "equity_curve": equity[-500:]
    }
