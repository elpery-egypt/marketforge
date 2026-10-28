"""
Provider contract for a future real data integration.

Implement this interface using a provider whose terms permit your intended use.
Do not put API secrets in frontend code.
"""
from typing import Protocol, Any

class MarketDataProvider(Protocol):
    async def historical_candles(self, symbol: str, timeframe: str, limit: int) -> list[dict[str, Any]]:
        ...

    async def subscribe(self, symbol: str, timeframe: str):
        """Yield normalized candle/tick events from a provider WebSocket."""
        ...
