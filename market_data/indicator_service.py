import logging

from database.repository import (
    CandleRepository,
    IndicatorRepository
)

from market_data.candle import Candle

from market_data.indicator_calculator import (
    IndicatorCalculator,
    IndicatorValues
)


class IndicatorService:
    """
    Coordinates indicator calculation and persistence.

        Historical Candles
                ↓
        Calculator State Initialization
                ↓
        Live Completed Candle
                ↓
        IndicatorCalculator
                ↓
        IndicatorValues
                ↓
        IndicatorRepository
                ↓
            PostgreSQL

    Responsibilities:
        - Initialize indicator calculation state from
          historical candles.
        - Calculate indicators for completed candles.
        - Persist calculated indicators.
        - Return calculated IndicatorValues.
        - Reset calculation state when required.

    This service does NOT handle:
        - PostgreSQL connections directly.
        - Upstox WebSocket connections.
        - Tick processing.
        - Candle aggregation.
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

        self.calculator = IndicatorCalculator()

    # ======================================================
    # INITIALIZE INDICATOR STATE
    # ======================================================

    def initialize(
        self,
        instrument_id: int,
        timeframe: str = "1m",
        limit: int = 100
    ) -> int:
        """
        Initialize indicator calculation state from
        historical candles.

        Historical candles are processed chronologically.

        Indicators are NOT persisted during initialization.

        This method exists to restore the in-memory state
        required for live indicator calculation after
        application startup or calculator reset.

        Returns:
            Number of historical candles processed.
        """

        try:

            # --------------------------------------------------
            # Reset existing state
            # --------------------------------------------------

            self.calculator.reset(
                instrument_id,
                timeframe
            )

            # --------------------------------------------------
            # Load historical candles
            # --------------------------------------------------

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
                    "No historical candles available for "
                    "indicator initialization | "
                    f"instrument_id={instrument_id} | "
                    f"timeframe={timeframe}"
                )

                return 0

            processed = 0

            # --------------------------------------------------
            # Process oldest -> newest
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

                self.calculator.calculate(
                    candle
                )

                processed += 1

            # --------------------------------------------------
            # Logging
            # --------------------------------------------------

            self.logger.info(
                "Indicator state initialized | "
                f"instrument_id={instrument_id} | "
                f"timeframe={timeframe} | "
                f"candles={processed}"
            )

            return processed

        except Exception:

            self.logger.exception(
                "Failed to initialize indicator state | "
                f"instrument_id={instrument_id} | "
                f"timeframe={timeframe}"
            )

            raise

    # ======================================================
    # PROCESS COMPLETED CANDLE
    # ======================================================

    def process_candle(
        self,
        candle: Candle
    ) -> IndicatorValues:
        """
        Calculate and persist indicators for one
        completed candle.

        The IndicatorCalculator maintains calculation
        state independently for each instrument/timeframe.

        The candle must be a completed candle and should
        arrive in chronological order for each
        instrument/timeframe.
        """

        try:

            # --------------------------------------------------
            # Calculate indicators
            # --------------------------------------------------

            values = self.calculator.calculate(
                candle
            )

            # --------------------------------------------------
            # Persist indicators
            # --------------------------------------------------

            indicator_id = (
                self.indicator_repository
                .upsert_indicators(
                    instrument_id=candle.instrument_id,
                    timestamp=candle.timestamp,
                    timeframe=candle.timeframe,
                    values=values
                )
            )

            # --------------------------------------------------
            # Logging
            # --------------------------------------------------

            self.logger.info(
                "Indicators saved | "
                f"indicator_id={indicator_id} | "
                f"instrument_id={candle.instrument_id} | "
                f"timeframe={candle.timeframe} | "
                f"timestamp={candle.timestamp} | "
                f"EMA9={values.ema_9} | "
                f"EMA20={values.ema_20} | "
                f"EMA50={values.ema_50} | "
                f"RSI14={values.rsi_14} | "
                f"ATR14={values.atr_14} | "
                f"VolumeSMA20={values.volume_sma_20} | "
                f"VWAP={values.vwap}"
            )

            return values

        except Exception:

            self.logger.exception(
                "Failed to calculate or persist indicators | "
                f"instrument_id={candle.instrument_id} | "
                f"timeframe={candle.timeframe} | "
                f"timestamp={candle.timestamp}"
            )

            raise

    def process_historical_candles(
        self,
        instrument_id: int,
        timeframe: str,
        candles: list,
        start_timestamp,
        persist_timestamps: set
    ) -> int:
        """
        Calculate and persist indicators for historical
        candles in chronological order.
        """

        historical_calculator = IndicatorCalculator()

        # --------------------------------------------------
        # Load warm-up candles before the backfill period
        # --------------------------------------------------

        warmup_rows = (
            self.candle_repository
            .get_candles_before(
                instrument_id=instrument_id,
                timeframe=timeframe,
                before_timestamp=start_timestamp,
                limit=100
            )
        )

        # --------------------------------------------------
        # Initialize historical calculator state
        # --------------------------------------------------

        for row in reversed(warmup_rows):

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

            historical_calculator.calculate(
                candle
            )

        # --------------------------------------------------
        # Process backfill candles chronologically
        # --------------------------------------------------

        processed = 0

        for candle in sorted(
            candles,
            key=lambda item: item.timestamp
        ):

            values = historical_calculator.calculate(
                candle
            )
            
            if candle.timestamp in persist_timestamps:
            
                self.indicator_repository.upsert_indicators(
                    instrument_id=candle.instrument_id,
                    timestamp=candle.timestamp,
                    timeframe=candle.timeframe,
                    values=values
                )
            
                processed += 1

        return processed

    # ======================================================
    # RESET
    # ======================================================

    def reset(
        self,
        instrument_id: int,
        timeframe: str
    ) -> None:
        """
        Reset indicator calculation state for one
        instrument/timeframe combination.
        """

        self.calculator.reset(
            instrument_id,
            timeframe
        )

        self.logger.info(
            "Indicator state reset | "
            f"instrument_id={instrument_id} | "
            f"timeframe={timeframe}"
        )