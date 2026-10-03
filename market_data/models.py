from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class MarketTick:
    """
    Provider-independent representation of a market tick.

    The rest of the application works with this model,
    regardless of whether the data comes from Upstox,
    Kite, Dhan, or another provider.
    """

    instrument_id: int
    timestamp: datetime

    last_price: Optional[float] = None
    last_quantity: Optional[int] = None
    volume: Optional[int] = None

    bid_price: Optional[float] = None
    ask_price: Optional[float] = None

    open_price: Optional[float] = None
    high_price: Optional[float] = None
    low_price: Optional[float] = None
    previous_close: Optional[float] = None