import logging

from database.repository import (
    CandleRepository,
    IndicatorRepository
)

from market_data.candle import Candle
from market_data.indicator_calculator import (
    IndicatorCalculator
)


class IndicatorBackfillService:
    """
    Recalculates indicators from historical candles.

    Historical candles must be processed chronologically
    because IndicatorCalculator maintains state.
    """

    def __init__(
        self,
        candle_repository: CandleRepository,
        indicator_repository: IndicatorRepository
    ) -> None:

        self.logger = logging.getLogger(
            self.__class__.__name__
        )

        self.candle_repository = (
            candle_repository
        )

        self.indicator_repository = (
            indicator_repository
        )

        self.calculator = (
            IndicatorCalculator()
        )

    # --------------------------------------------------
    # Backfill
    # --------------------------------------------------

    def backfill(
        self,
        instrument_id: int,
        timeframe: str = "1m",
        limit: int = 100
    ) -> int:
        """
        Recalculate indicators for historical candles.

        Candles are processed oldest -> newest.
        """

        candles = (
            self.candle_repository
            .get_candles_chronological(
                instrument_id=instrument_id,
                timeframe=timeframe,
                limit=limit
            )
        )

        if not candles:

            self.logger.info(
                "No candles found for backfill | "
                f"instrument_id={instrument_id} | "
                f"timeframe={timeframe}"
            )

            return 0

        # --------------------------------------------------
        # Reset calculation state
        # --------------------------------------------------

        self.calculator.reset(
            instrument_id,
            timeframe
        )

        processed = 0

        # --------------------------------------------------
        # Process chronologically
        # --------------------------------------------------

        for row in candles:

            candle = Candle(
                instrument_id=row[1],
                timestamp=row[2],
                timeframe=row[3],
                open_price=row[4],
                high_price=row[5],
                low_price=row[6],
                close_price=row[7],
                volume=row[8]
            )

            values = (
                self.calculator.calculate(
                    candle
                )
            )

            self.indicator_repository.upsert_indicators(
                instrument_id=candle.instrument_id,
                timestamp=candle.timestamp,
                timeframe=candle.timeframe,
                values=values
            )

            processed += 1

        self.logger.info(
            "Indicator backfill completed | "
            f"instrument_id={instrument_id} | "
            f"timeframe={timeframe} | "
            f"candles={processed}"
        )

        return processed