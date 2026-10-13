import logging
from datetime import datetime

from config.settings import Settings

from database.connection import DatabaseConnection

from database.repository import (
    CandleRepository,
    IndicatorRepository,
    InstrumentRepository
)

from market_data.candle import Candle

from market_data.indicator_service import (
    IndicatorService
)

from market_data.upstox_backfill_provider import (
    UpstoxBackfillProvider
)


# ==================================================
# BACKFILL CONFIGURATION
# ==================================================

# --------------------------------------------------
# Hardcode the historical period to backfill here.
# --------------------------------------------------

BACKFILL_START_DATE = "2026-09-25"
BACKFILL_END_DATE = "2026-10-05"

BACKFILL_INTERVAL = "1"


# ==================================================
# Logging
# ==================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(name)s | "
        "%(message)s"
    )
)


logger = logging.getLogger(
    "Backfill"
)


# ==================================================
# Convert Upstox candles
# ==================================================

def convert_to_candles(
    instrument_id: int,
    raw_candles: list
) -> list[Candle]:
    """
    Convert Upstox historical candle arrays
    into project Candle objects.
    """

    candles = []

    for raw_candle in raw_candles:

        candles.append(
            Candle(
                instrument_id=instrument_id,
                timestamp=datetime.fromisoformat(
                    raw_candle[0]
                ),
                timeframe="1m",
                open_price=raw_candle[1],
                high_price=raw_candle[2],
                low_price=raw_candle[3],
                close_price=raw_candle[4],
                volume=raw_candle[5]
            )
        )

    return candles


# ==================================================
# Backfill timestamp range
# ==================================================

def get_backfill_timestamps():
    """
    Return the timestamp boundaries used for
    historical indicator processing.

    The market session is:

        09:15 -> 15:30 IST

    The end timestamp is exclusive.
    """

    timezone = Settings.MARKET_TIMEZONE

    start_timestamp = datetime.fromisoformat(
        f"{BACKFILL_START_DATE}T09:15:00+05:30"
    )

    end_timestamp = datetime.fromisoformat(
        f"{BACKFILL_END_DATE}T15:30:00+05:30"
    )

    return (
        start_timestamp,
        end_timestamp
    )


# ==================================================
# Main
# ==================================================

def main() -> None:

    logger.info(
        "=================================================="
    )

    logger.info(
        "Historical candle + indicator backfill started"
    )

    logger.info(
        f"Start date: {BACKFILL_START_DATE}"
    )

    logger.info(
        f"End date:   {BACKFILL_END_DATE}"
    )

    logger.info(
        f"Interval:   {BACKFILL_INTERVAL} minute"
    )

    logger.info(
        "=================================================="
    )

    db = DatabaseConnection()

    candle_repository = CandleRepository(
        db
    )

    indicator_repository = IndicatorRepository(
        db
    )

    instrument_repository = InstrumentRepository(
        db
    )

    indicator_service = IndicatorService(
        candle_repository=candle_repository,
        indicator_repository=indicator_repository
    )

    provider = UpstoxBackfillProvider()

    try:

        instruments = (
            instrument_repository
            .get_active_instruments_with_provider_ids()
        )

        logger.info(
            "Active instruments loaded | "
            f"count={len(instruments)}"
        )

        # --------------------------------------------------
        # Backfill boundaries
        # --------------------------------------------------

        (
            start_timestamp,
            end_timestamp
        ) = get_backfill_timestamps()

        # --------------------------------------------------
        # Statistics
        # --------------------------------------------------

        total_received = 0
        total_inserted = 0
        total_skipped = 0
        total_indicators_processed = 0

        successful_instruments = 0
        failed_instruments = 0

        # --------------------------------------------------
        # Process every active instrument
        # --------------------------------------------------

        for (
            instrument_id,
            provider_instrument_id
        ) in instruments:

            logger.info(
                "--------------------------------------------------"
            )

            logger.info(
                "Processing historical data | "
                f"instrument_id={instrument_id} | "
                f"provider={provider_instrument_id}"
            )

            try:

                # --------------------------------------------------
                # Fetch historical candles from Upstox
                # --------------------------------------------------

                raw_candles = (
                    provider
                    .get_historical_candles(
                        instrument_key=(
                            provider_instrument_id
                        ),
                        start_date=(
                            BACKFILL_START_DATE
                        ),
                        end_date=(
                            BACKFILL_END_DATE
                        ),
                        interval=(
                            BACKFILL_INTERVAL
                        )
                    )
                )

                total_received += (
                    len(raw_candles)
                )

                # --------------------------------------------------
                # Convert to project Candle objects
                # --------------------------------------------------

                candles = convert_to_candles(
                    instrument_id=instrument_id,
                    raw_candles=raw_candles
                )

                # --------------------------------------------------
                # Keep only requested market-session candles
                # --------------------------------------------------

                candles = [
                    candle
                    for candle in candles
                    if (
                        candle.timestamp >= start_timestamp
                        and candle.timestamp < end_timestamp
                    )
                ]

                # --------------------------------------------------
                # Persist missing candles
                # --------------------------------------------------

                inserted, skipped = (
                    candle_repository
                    .insert_candles_if_missing(
                        candles
                    )
                )

                total_inserted += inserted
                total_skipped += skipped

                logger.info(
                    "Historical candles persisted | "
                    f"instrument_id={instrument_id} | "
                    f"received={len(candles)} | "
                    f"inserted={inserted} | "
                    f"skipped={skipped}"
                )

                # --------------------------------------------------
                # Determine which indicator timestamps need
                # to be persisted.
                #
                # We use the timestamps of the historical candles.
                # IndicatorService calculates the entire sequence
                # chronologically, while persistence is handled
                # through upsert.
                # --------------------------------------------------

                persist_timestamps = {
                    candle.timestamp
                    for candle in candles
                }

                # --------------------------------------------------
                # Calculate historical indicators
                #
                # IndicatorService loads warm-up candles before
                # BACKFILL_START_DATE and then processes the
                # complete historical candle sequence chronologically.
                # --------------------------------------------------

                indicators_processed = (
                    indicator_service
                    .process_historical_candles(
                        instrument_id=instrument_id,
                        timeframe="1m",
                        candles=candles,
                        start_timestamp=start_timestamp,
                        persist_timestamps=(
                            persist_timestamps
                        )
                    )
                )

                total_indicators_processed += (
                    indicators_processed
                )

                logger.info(
                    "Historical indicators processed | "
                    f"instrument_id={instrument_id} | "
                    f"count={indicators_processed}"
                )

                successful_instruments += 1

            except Exception:

                failed_instruments += 1

                logger.exception(
                    "Historical backfill failed | "
                    f"instrument_id={instrument_id}"
                )

        # --------------------------------------------------
        # Final summary
        # --------------------------------------------------

        logger.info(
            "=================================================="
        )

        logger.info(
            "Historical candle + indicator backfill completed"
        )

        logger.info(
            f"Instruments processed: "
            f"{len(instruments)}"
        )

        logger.info(
            f"Successful instruments: "
            f"{successful_instruments}"
        )

        logger.info(
            f"Failed instruments: "
            f"{failed_instruments}"
        )

        logger.info(
            f"Total candles received: "
            f"{total_received}"
        )

        logger.info(
            f"Total candles inserted: "
            f"{total_inserted}"
        )

        logger.info(
            f"Total candles skipped: "
            f"{total_skipped}"
        )

        logger.info(
            f"Total indicators processed: "
            f"{total_indicators_processed}"
        )

        logger.info(
            "=================================================="
        )

    finally:

        db.close()


if __name__ == "__main__":
    main()