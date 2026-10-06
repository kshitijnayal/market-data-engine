import logging
from typing import Optional

from database.repository import (
    CandleRepository,
    IndicatorRepository
)

from market_data.models import MarketTick
from market_data.candle import Candle
from market_data.candle_aggregator import CandleAggregator
from market_data.indicator_service import (
    IndicatorService,
    IndicatorValues
)


class CandleService:
    """
    Coordinates the market tick -> candle -> indicator flow.

        MarketTick
            ↓
        CandleAggregator
            ↓
        completed Candle
            ↓
        CandleRepository
            ↓
        IndicatorService
            ↓
        IndicatorRepository

    Responsibilities:
        - Receive market ticks.
        - Aggregate ticks into candles.
        - Persist completed candles.
        - Calculate and persist indicators for
          completed candles.

    This service does NOT handle:
        - PostgreSQL connections directly.
        - Upstox WebSocket connections.
        - Raw tick persistence.
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

        self.indicator_service = (
            IndicatorService(
                candle_repository=candle_repository,
                indicator_repository=indicator_repository
            )
        )

        self.aggregator = CandleAggregator()

    # --------------------------------------------------
    # Process tick
    # --------------------------------------------------

    def process_tick(
        self,
        tick: MarketTick,
        timeframe: str = "1m"
    ) -> Optional[IndicatorValues]:
        """
        Process one market tick.

        A tick may update the currently open candle.
        When a new time bucket begins, the previous candle
        is completed, persisted, and passed to the
        IndicatorService.

        Returns:
            IndicatorValues when a candle was completed.
            None when the current candle remains open.
        """

        try:

            completed_candle = (
                self.aggregator.process_tick(
                    tick=tick,
                    timeframe=timeframe
                )
            )

            # --------------------------------------------------
            # No completed candle yet
            # --------------------------------------------------

            if completed_candle is None:

                return None

            # --------------------------------------------------
            # Persist completed candle
            # --------------------------------------------------

            candle_id = (
                self.candle_repository
                .upsert_candle(
                    completed_candle
                )
            )

            # --------------------------------------------------
            # Calculate and persist indicators
            # --------------------------------------------------

            indicator_values = (
                self.indicator_service
                .process_candle(
                    completed_candle
                )
            )

            # --------------------------------------------------
            # Logging
            # --------------------------------------------------

            self.logger.info(
                "Candle completed | "
                f"candle_id={candle_id} | "
                f"instrument_id="
                f"{completed_candle.instrument_id} | "
                f"timeframe="
                f"{completed_candle.timeframe} | "
                f"timestamp="
                f"{completed_candle.timestamp}"
            )

            return indicator_values

        except Exception:

            self.logger.exception(
                "Failed to process market tick | "
                f"instrument_id={tick.instrument_id} | "
                f"timestamp={tick.timestamp} | "
                f"timeframe={timeframe}"
            )

            raise

    # --------------------------------------------------
    # Flush
    # --------------------------------------------------

    def flush(self) -> list[Candle]:
        """
        Flush all currently open candles.

        The returned candles are NOT automatically persisted
        or passed to the indicator service.

        This method is intended for controlled shutdown or
        explicit lifecycle handling.
        """

        return self.aggregator.flush()

    def flush_and_persist(self) -> list[Candle]:
        """
        Flush all open candles, persist them, and process through
        indicator service.

        Used during application shutdown to ensure no candles
        or indicators are lost.

        Returns:
            List of flushed candles.
        """

        try:

            remaining_candles = self.aggregator.flush()

            if not remaining_candles:

                return remaining_candles

            self.logger.info(
                f"Flushing {len(remaining_candles)} "
                f"remaining candles..."
            )

            # --------------------------------------------------
            # Persist each candle and process indicators
            # --------------------------------------------------

            for candle in remaining_candles:

                candle_id = (
                    self.candle_repository
                    .upsert_candle(candle)
                )

                self.indicator_service.process_candle(
                    candle
                )

                self.logger.debug(
                    f"Flushed candle persisted | "
                    f"candle_id={candle_id} | "
                    f"instrument_id={candle.instrument_id} | "
                    f"timestamp={candle.timestamp}"
                )

            self.logger.info(
                f"Candle flush complete | "
                f"count={len(remaining_candles)}"
            )

            return remaining_candles

        except Exception:

            self.logger.exception(
                "Failed to flush and persist remaining candles."
            )

            raise

    # --------------------------------------------------
    # Reset indicators
    # --------------------------------------------------

    def reset_indicators(
        self,
        instrument_id: int,
        timeframe: str
    ) -> None:
        """
        Reset indicator calculation state for one
        instrument/timeframe combination.
        """

        self.indicator_service.reset(
            instrument_id=instrument_id,
            timeframe=timeframe
        )