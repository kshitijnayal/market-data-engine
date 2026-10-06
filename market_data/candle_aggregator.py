from datetime import datetime

from market_data.candle import Candle
from market_data.models import MarketTick


class CandleAggregator:
    """
    Converts MarketTick objects into OHLCV candles.

    The provider's volume is cumulative traded volume, so
    candle volume is calculated from volume deltas.
    """

    def __init__(self):

        # (instrument_id, timeframe) -> current Candle
        self._candles = {}

        # instrument_id -> previous cumulative provider volume
        self._last_volume = {}

    # --------------------------------------------------
    # Process tick
    # --------------------------------------------------

    def process_tick(
        self,
        tick: MarketTick,
        timeframe: str = "1m"
    ) -> Candle | None:

        bucket_timestamp = (
            self._get_bucket_timestamp(
                tick.timestamp,
                timeframe
            )
        )

        key = (
            tick.instrument_id,
            timeframe
        )

        volume_delta = self._calculate_volume_delta(
            tick.instrument_id,
            tick.volume
        )

        current = self._candles.get(key)

        # --------------------------------------------------
        # First tick for this instrument/timeframe
        # --------------------------------------------------

        if current is None:

            self._candles[key] = Candle(
                instrument_id=tick.instrument_id,
                timestamp=bucket_timestamp,
                timeframe=timeframe,
                open_price=tick.last_price,
                high_price=tick.last_price,
                low_price=tick.last_price,
                close_price=tick.last_price,
                volume=volume_delta
            )

            return None

        # --------------------------------------------------
        # Same candle
        # --------------------------------------------------

        if current.timestamp == bucket_timestamp:

            self._update_candle(
                current,
                tick,
                volume_delta
            )

            return None

        # --------------------------------------------------
        # New candle
        # --------------------------------------------------

        completed_candle = current

        self._candles[key] = Candle(
            instrument_id=tick.instrument_id,
            timestamp=bucket_timestamp,
            timeframe=timeframe,
            open_price=tick.last_price,
            high_price=tick.last_price,
            low_price=tick.last_price,
            close_price=tick.last_price,
            volume=volume_delta
        )

        return completed_candle

    # --------------------------------------------------
    # Flush
    # --------------------------------------------------

    def flush(self) -> list[Candle]:
        """
        Return all currently open candles.

        Used during application shutdown.
        """

        candles = list(
            self._candles.values()
        )

        self._candles.clear()

        return candles

    # --------------------------------------------------
    # Volume
    # --------------------------------------------------

    def _calculate_volume_delta(
        self,
        instrument_id: int,
        current_volume: int | None
    ) -> int:

        if current_volume is None:

            return 0

        previous_volume = (
            self._last_volume.get(
                instrument_id
            )
        )

        self._last_volume[instrument_id] = (
            current_volume
        )

        # First observed volume
        if previous_volume is None:

            return 0

        # Normal cumulative-volume increase
        if current_volume >= previous_volume:

            return (
                current_volume
                - previous_volume
            )

        # Provider/session volume reset
        return current_volume

    # --------------------------------------------------
    # Update candle
    # --------------------------------------------------

    @staticmethod
    def _update_candle(
        candle: Candle,
        tick: MarketTick,
        volume_delta: int
    ) -> None:

        price = tick.last_price

        if price is not None:

            if candle.open_price is None:

                candle.open_price = price

            if (
                candle.high_price is None
                or price > candle.high_price
            ):

                candle.high_price = price

            if (
                candle.low_price is None
                or price < candle.low_price
            ):

                candle.low_price = price

            candle.close_price = price

        # Add only the volume traded since
        # the previous tick.
        candle.volume = (
            (candle.volume or 0)
            + volume_delta
        )

    # --------------------------------------------------
    # Time bucket
    # --------------------------------------------------

    @staticmethod
    def _get_bucket_timestamp(
        timestamp: datetime,
        timeframe: str
    ) -> datetime:

        if not timeframe.endswith("m"):

            raise ValueError(
                f"Unsupported timeframe: {timeframe}"
            )

        minutes = int(
            timeframe[:-1]
        )

        if minutes <= 0:

            raise ValueError(
                f"Invalid timeframe: {timeframe}"
            )

        bucket_minute = (
            timestamp.minute
            - timestamp.minute % minutes
        )

        return timestamp.replace(
            minute=bucket_minute,
            second=0,
            microsecond=0
        )