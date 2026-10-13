from datetime import datetime, timedelta, timezone
from typing import List

from market_data.base_provider import MarketDataProvider
from market_data.models import MarketTick


class TestMarketDataProvider(MarketDataProvider):
    """
    Deterministic market-data provider used for testing.

    This provider does not connect to any external service.

    It generates synthetic MarketTick objects and emits them
    through the callback registered with set_tick_callback().
    """
    __test__ = False

    def __init__(
        self,
        instrument_ids: List[int] | None = None
    ) -> None:
    
        super().__init__()
    
        self._connected = False
    
        self._subscribed_instruments: List[str] = []
    
        self._volume = 1000
    
        self.instrument_ids = (
            instrument_ids or []
        )

    # ======================================================
    # CONNECT
    # ======================================================

    def connect(self) -> None:
        """
        Simulate connecting to a market-data provider.
        """

        self._connected = True

    # ======================================================
    # SUBSCRIBE
    # ======================================================

    def subscribe(
        self,
        instruments: List[str]
    ) -> None:
        """
        Subscribe to instruments and emit synthetic ticks.

        Each subscribed instrument receives one deterministic
        test tick.
        """

        if not self._connected:

            raise RuntimeError(
                "TestMarketDataProvider is not connected."
            )

        self._subscribed_instruments = list(
            instruments
        )

        timestamp = datetime.now(
            timezone.utc
        )

        for index, instrument in enumerate(
            self._subscribed_instruments
        ):

            try:

                instrument_id = int(
                    instrument
                )

            except (TypeError, ValueError):

                raise ValueError(
                    "Test provider instruments must "
                    "contain numeric instrument IDs."
                )

            price = (
                100.0
                + index
            )

            self._volume += 10

            tick = MarketTick(
                instrument_id=instrument_id,
                timestamp=(
                    timestamp
                    + timedelta(
                        seconds=index
                    )
                ),
                last_price=price,
                last_quantity=10,
                volume=self._volume
            )

            self._emit_tick(
                tick
            )

    # ======================================================
    # DISCONNECT
    # ======================================================

    def disconnect(self) -> None:
        """
        Simulate disconnecting from the provider.
        """

        self._connected = False