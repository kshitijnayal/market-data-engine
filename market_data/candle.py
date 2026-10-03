from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Candle:
    """
    Provider-independent OHLCV candle.

    A candle represents aggregated market data
    for one instrument and one timeframe.
    """

    instrument_id: int
    timestamp: datetime
    timeframe: str

    open_price: Optional[float] = None
    high_price: Optional[float] = None
    low_price: Optional[float] = None
    close_price: Optional[float] = None

    volume: Optional[int] = None