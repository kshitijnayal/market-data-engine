import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from config.settings import Settings
from database.connection import DatabaseConnection
from database.repository import (
    CandleRepository,
    IndicatorRepository,
    InstrumentRepository
)

from market_data.candle_gap_detector import (
    find_missing_candles,
    filter_missing_candles
)

from market_data.indicator_service import (
    IndicatorService
)

from market_data.upstox_historical_provider import (
    UpstoxHistoricalProvider
)


def get_recovery_window():
    """
    Return today's market-session recovery window.

    Start:
        Market open.

    End:
        Latest completed 1-minute boundary.

    The current in-progress minute is excluded.
    """

    timezone = ZoneInfo(
        Settings.MARKET_TIMEZONE
    )

    now = datetime.now(timezone)

    market_open = datetime.strptime(
        Settings.MARKET_OPEN,
        "%H:%M"
    ).time()

    market_close = datetime.strptime(
        Settings.MARKET_CLOSE,
        "%H:%M"
    ).time()

    start_timestamp = datetime(
        now.year,
        now.month,
        now.day,
        market_open.hour,
        market_open.minute,
        tzinfo=timezone
    )

    market_close_timestamp = datetime(
        now.year,
        now.month,
        now.day,
        market_close.hour,
        market_close.minute,
        tzinfo=timezone
    )

    current_minute = now.replace(
        second=0,
        microsecond=0
    )

    if current_minute <= start_timestamp:
        return None

    if current_minute > market_close_timestamp:
        end_timestamp = market_close_timestamp
    else:
        end_timestamp = current_minute

    if end_timestamp <= start_timestamp:
        return None

    return (
        start_timestamp,
        end_timestamp
    )


def recover_current_session() -> dict:
    """
    Recover missing current-session candles and indicators.

    Returns:
        Dictionary containing recovery statistics.
    """

    recovery_window = get_recovery_window()

    if recovery_window is None:
        return {
            "missing_candles": 0,
            "recoverable_candles": 0,
            "candles_inserted": 0,
            "candles_skipped": 0,
            "indicators_processed": 0
        }

    (
        start_timestamp,
        end_timestamp
    ) = recovery_window

    db = DatabaseConnection()

    candle_repository = CandleRepository(db)

    indicator_repository = IndicatorRepository(db)

    instrument_repository = InstrumentRepository(db)

    historical_provider = UpstoxHistoricalProvider()

    indicator_service = IndicatorService(
        candle_repository=candle_repository,
        indicator_repository=indicator_repository
    )

    total_missing = 0
    total_recoverable = 0
    total_inserted = 0
    total_skipped = 0
    total_indicators = 0

    try:

        instruments = (
            instrument_repository
            .get_active_instruments_with_provider_ids()
        )

        logging.info(
            "Current-session recovery started | "
            f"start={start_timestamp} | "
            f"end={end_timestamp} | "
            f"instruments={len(instruments)}"
        )

        for instrument_id, provider_instrument_id in instruments:

            logging.info(
                "Checking recovery gaps | "
                f"instrument_id={instrument_id}"
            )

            missing = find_missing_candles(
                candle_repository=candle_repository,
                instrument_id=instrument_id,
                timeframe="1m",
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp
            )

            if not missing:
                continue

            logging.info(
                "Missing candles detected | "
                f"instrument_id={instrument_id} | "
                f"count={len(missing)}"
            )

            total_missing += len(missing)

            historical_raw = (
                historical_provider
                .get_intraday_candles(
                    instrument_key=provider_instrument_id,
                    interval="1"
                )
            )

            historical_candles = (
                historical_provider
                .convert_to_candles(
                    instrument_id=instrument_id,
                    candles=historical_raw
                )
            )

            historical_candles = [
                candle
                for candle in historical_candles
                if (
                    candle.timestamp >= start_timestamp
                    and candle.timestamp < end_timestamp
                )
            ]

            recoverable = (
                filter_missing_candles(
                    candles=historical_candles,
                    missing_timestamps=missing
                )
            )

            logging.info(
                "Historical recovery result | "
                f"instrument_id={instrument_id} | "
                f"available={len(historical_candles)} | "
                f"recoverable={len(recoverable)}"
            )

            total_recoverable += len(recoverable)

            if not recoverable:
                logging.warning(
                    "No historical candles available for "
                    f"missing timestamps | "
                    f"instrument_id={instrument_id}"
                )
                continue

            inserted, skipped = (
                candle_repository
                .insert_candles_if_missing(
                    recoverable
                )
            )

            logging.info(
                "Candle recovery persisted | "
                f"instrument_id={instrument_id} | "
                f"inserted={inserted} | "
                f"skipped={skipped}"
            )

            total_inserted += inserted
            total_skipped += skipped

            persist_timestamps = {
                candle.timestamp
                for candle in recoverable
            }

            indicators_processed = (
                indicator_service
                .process_historical_candles(
                    instrument_id=instrument_id,
                    timeframe="1m",
                    candles=historical_candles,
                    start_timestamp=start_timestamp,
                    persist_timestamps=persist_timestamps
                )
            )

            logging.info(
                "Historical indicators processed | "
                f"instrument_id={instrument_id} | "
                f"count={indicators_processed}"
            )

            total_indicators += (
                indicators_processed
            )

        logging.info(
            "Current-session recovery completed | "
            f"missing={total_missing} | "
            f"recoverable={total_recoverable} | "
            f"inserted={total_inserted} | "
            f"skipped={total_skipped} | "
            f"indicators={total_indicators}"
        )

        return {
            "missing_candles": total_missing,
            "recoverable_candles": total_recoverable,
            "candles_inserted": total_inserted,
            "candles_skipped": total_skipped,
            "indicators_processed": total_indicators
        }

    finally:
        db.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "%(message)s"
        )
    )

    recovery_window = get_recovery_window()

    if recovery_window is None:
        print(
            "No completed market-session minute "
            "is available for recovery."
        )
        return

    (
        start_timestamp,
        end_timestamp
    ) = recovery_window

    print("")
    print(
        "========== CURRENT SESSION RECOVERY =========="
    )

    print(
        f"Start: {start_timestamp}"
    )

    print(
        f"End:   {end_timestamp}"
    )

    print("")

    results = recover_current_session()

    print("")
    print(
        "============== RECOVERY SUMMARY =============="
    )

    print(
        f"Missing candles detected: "
        f"{results['missing_candles']}"
    )

    print(
        f"Recoverable candles: "
        f"{results['recoverable_candles']}"
    )

    print(
        f"Candles inserted: "
        f"{results['candles_inserted']}"
    )

    print(
        f"Candles skipped: "
        f"{results['candles_skipped']}"
    )

    print(
        f"Indicators processed: "
        f"{results['indicators_processed']}"
    )

    print(
        "==============================================="
    )


if __name__ == "__main__":
    main()