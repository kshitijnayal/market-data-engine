import logging
from threading import Lock

from database.connection import DatabaseConnection
from database.repository import (
    IndicatorRepository,
    InstrumentRepository,
    TickRepository,
    CandleRepository
)
from market_data.models import MarketTick
from market_data.upstox_provider import UpstoxProvider
from market_data.candle_aggregator import CandleAggregator
from market_data.indicator_service import IndicatorService


class MarketDataService:
    """
    Coordinates:

        PostgreSQL instruments
                ↓
        Upstox WebSocket
                ↓
            MarketTick
                ↓
        ┌───────────────────────┐
        │                       │
        ↓                       ↓
    Tick Buffer          CandleAggregator
        ↓                       ↓
    PostgreSQL ticks     Completed Candle
                                ↓
                         PostgreSQL candles

    This service owns the market-data ingestion flow.
    """

    # --------------------------------------------------
    # Batch configuration
    # --------------------------------------------------

    TICK_BATCH_SIZE = 250

    def __init__(self, provider=None):

        self.logger = logging.getLogger(
            self.__class__.__name__
        )

        # --------------------------------------------------
        # Database
        # --------------------------------------------------

        self.db = DatabaseConnection()

        self.instrument_repository = (
            InstrumentRepository(
                self.db
            )
        )

        self.tick_repository = (
            TickRepository(
                self.db
            )
        )

        self.candle_repository = (
            CandleRepository(
                self.db
            )
        )
        self.indicator_repository = (
            IndicatorRepository(
                self.db
            )
        )
        # --------------------------------------------------
        # Candle aggregation
        # --------------------------------------------------

        self.candle_aggregator = (
            CandleAggregator()
        )

        self.indicator_service = (
            IndicatorService(
                self.candle_repository,
                self.indicator_repository
            )
        )

        # --------------------------------------------------
        # Provider
        # --------------------------------------------------

        self.provider = provider

        # --------------------------------------------------
        # Tick buffer
        # --------------------------------------------------

        self._tick_buffer: list[MarketTick] = []

        self._buffer_lock = Lock()

        # --------------------------------------------------
        # Statistics
        # --------------------------------------------------

        self._total_ticks_received = 0
        self._total_ticks_persisted = 0

        # --------------------------------------------------
        # Failure state
        # --------------------------------------------------

        self._provider_failed = False

        # --------------------------------------------------
        # Lifecycle
        # --------------------------------------------------

        self._running = False

    # --------------------------------------------------
    # Start
    # --------------------------------------------------

    def start(self) -> None:

        if self._running:

            self.logger.warning(
                "Market-data service is already running."
            )

            return

        self.logger.info(
            "Starting market-data ingestion..."
        )
 
        # --------------------------------------------------
        # Load active Upstox instruments
        # --------------------------------------------------

        instrument_keys = (
            self.instrument_repository
            .get_active_provider_instrument_ids()
        )

        if not instrument_keys:

            raise RuntimeError(
                "No active provider instruments found."
            )

        self.logger.info(
            f"Active instruments loaded: "
            f"{len(instrument_keys)}"
        )

        # --------------------------------------------------
        # Initialize indicator calculation state
        # --------------------------------------------------
        
        instrument_ids = (
            self.instrument_repository
            .get_active_instrument_ids()
        )

        for instrument_id in instrument_ids:

            self.indicator_service.initialize(
                instrument_id=instrument_id,
                timeframe="1m",
                limit=100
            )

        # --------------------------------------------------
        # Create provider
        # --------------------------------------------------

        if self.provider is None:

            self.provider = UpstoxProvider(
                instrument_keys=instrument_keys,
                mode="full",
                instrument_repository=(
                    self.instrument_repository
                )
            )

        # --------------------------------------------------
        # Register tick callback
        # --------------------------------------------------

        self.provider.set_tick_callback(
            self._handle_tick
        )

        self.provider.set_failure_callback(
            self._handle_provider_failure
        )

        self._running = True

        # --------------------------------------------------
        # Connect
        # --------------------------------------------------

        self.logger.info(
            "Connecting to Upstox..."
        )

        try:

            self.provider.connect()

        except Exception:

            self._running = False
            self.provider = None

            raise

    def _handle_provider_failure(
        self,
        message: str
    ) -> None:
        """
        Handle an unrecoverable market-data provider failure.
        """

        self._provider_failed = True

        logging.critical(
            "Market-data provider failure | %s",
            message
        )

    # --------------------------------------------------
    # Tick handler
    # --------------------------------------------------

    def _handle_tick(
        self,
        tick: MarketTick
    ) -> None:
        
        if not self._running:
            return
        
        try:
        
            # --------------------------------------------------
            # Statistics
            # --------------------------------------------------
    
            self._total_ticks_received += 1
    
            # --------------------------------------------------
            # Add tick to buffer
            # --------------------------------------------------
    
            batch = None
    
            with self._buffer_lock:
            
                self._tick_buffer.append(tick)
    
                if len(self._tick_buffer) >= self.TICK_BATCH_SIZE:
                
                    batch = self._tick_buffer
    
                    self._tick_buffer = []
    
            # --------------------------------------------------
            # Persist completed tick batch
            # --------------------------------------------------
    
            if batch:
            
                self._persist_batch(
                    batch
                )
    
            # --------------------------------------------------
            # Aggregate into 1-minute candle
            # --------------------------------------------------
    
            completed_candle = (
                self.candle_aggregator.process_tick(
                    tick,
                    timeframe="1m"
                )
            )
    
            # --------------------------------------------------
            # Persist completed candle
            # --------------------------------------------------
    
            if completed_candle is not None:
            
                self.candle_repository.upsert_candle(
                    completed_candle
                )
    
                self.logger.info(
                    f"Candle saved | "
                    f"instrument_id="
                    f"{completed_candle.instrument_id} | "
                    f"timeframe="
                    f"{completed_candle.timeframe} | "
                    f"timestamp="
                    f"{completed_candle.timestamp} | "
                    f"O="
                    f"{completed_candle.open_price} | "
                    f"H="
                    f"{completed_candle.high_price} | "
                    f"L="
                    f"{completed_candle.low_price} | "
                    f"C="
                    f"{completed_candle.close_price} | "
                    f"V="
                    f"{completed_candle.volume}"
                )
    
                # --------------------------------------------------
                # Calculate + persist indicators
                # --------------------------------------------------
    
                self.indicator_service.process_candle(
                    completed_candle
                )
    
        except Exception:
        
            self.logger.exception(
                "Failed to process market tick."
            )

    # --------------------------------------------------
    # Batch persistence
    # --------------------------------------------------

    def _persist_batch(
        self,
        batch: list[MarketTick]
    ) -> None:

        if not batch:

            return

        inserted = self.tick_repository.save_ticks(
            batch
        )
        
        self._total_ticks_persisted += inserted

        self.logger.info(
            f"Tick batch persisted | "
            f"received={len(batch)} | "
            f"inserted={inserted} | "
            f"duplicates_ignored={len(batch) - inserted} | "
            f"total_persisted={self._total_ticks_persisted}"
        )

    # --------------------------------------------------
    # Flush remaining ticks
    # --------------------------------------------------

    def _flush_tick_buffer(self) -> None:

        batch = None

        with self._buffer_lock:

            if self._tick_buffer:

                batch = self._tick_buffer

                self._tick_buffer = []

        if batch:

            self.logger.info(
                f"Flushing remaining ticks | "
                f"size={len(batch)}"
            )

            self._persist_batch(
                batch
            )

    # --------------------------------------------------
    # Stop
    # --------------------------------------------------

    def stop(self) -> None:

        if not self._running:

            self.logger.info(
                "Market-data service is not running."
            )

            return

        self.logger.info(
            "Stopping market-data ingestion..."
        )

        # --------------------------------------------------
        # Stop accepting new ticks
        # --------------------------------------------------

        self._running = False

        # --------------------------------------------------
        # Disconnect provider FIRST
        # --------------------------------------------------

        if self.provider:

            self.provider.disconnect()

            self.provider = None

        # --------------------------------------------------
        # Flush remaining raw ticks
        # --------------------------------------------------

        self._flush_tick_buffer()

        # --------------------------------------------------
        # Flush open candles
        # --------------------------------------------------

        if self.candle_aggregator:

            remaining_candles = (
                self.candle_aggregator.flush()
            )

            for candle in remaining_candles:

                self.candle_repository.upsert_candle(
                    candle
                )
                self.indicator_service.process_candle(
                    candle
                )

            self.logger.info(
                f"Flushed remaining candles | "
                f"count="
                f"{len(remaining_candles)}"
            )

        # --------------------------------------------------
        # Statistics
        # --------------------------------------------------

        self.logger.info(
            f"Market-data statistics | "
            f"received="
            f"{self._total_ticks_received} | "
            f"persisted="
            f"{self._total_ticks_persisted}"
        )

        # --------------------------------------------------
        # Close database
        # --------------------------------------------------

        self.db.close()

        self.logger.info(
            "Market-data ingestion stopped."
        )