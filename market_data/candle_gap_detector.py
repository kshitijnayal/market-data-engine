from datetime import datetime, timedelta


def generate_expected_minutes(
    start_timestamp: datetime,
    end_timestamp: datetime
) -> list[datetime]:
    """
    Generate 1-minute timestamps from start inclusive
    to end exclusive.
    """

    timestamps = []

    current = start_timestamp

    while current < end_timestamp:

        timestamps.append(current)

        current += timedelta(
            minutes=1
        )

    return timestamps


def find_missing_minutes(
    expected_minutes: list[datetime],
    existing_minutes: set[datetime]
) -> list[datetime]:
    """
    Return expected timestamps that are not present
    in the database.
    """

    return [
        timestamp
        for timestamp in expected_minutes
        if timestamp not in existing_minutes
    ]


def find_missing_candles(
    candle_repository,
    instrument_id: int,
    timeframe: str,
    start_timestamp: datetime,
    end_timestamp: datetime
) -> list[datetime]:
    """
    Find missing candle timestamps for one instrument.
    """

    expected_minutes = generate_expected_minutes(
        start_timestamp=start_timestamp,
        end_timestamp=end_timestamp
    )

    existing_minutes = (
        candle_repository
        .get_candle_timestamps_between(
            instrument_id=instrument_id,
            timeframe=timeframe,
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp
        )
    )

    return find_missing_minutes(
        expected_minutes=expected_minutes,
        existing_minutes=existing_minutes
    )


def filter_missing_candles(
    candles: list,
    missing_timestamps: list[datetime]
) -> list:
    """
    Return only historical candles whose timestamps
    are missing from the database.
    """

    missing_set = set(
        missing_timestamps
    )

    return [
        candle
        for candle in candles
        if candle.timestamp in missing_set
    ]


if __name__ == "__main__":

    from database.connection import DatabaseConnection
    from database.repository import (
        CandleRepository,
        IndicatorRepository
    )

    from market_data.indicator_service import (
        IndicatorService
    )

    from market_data.upstox_historical_provider import (
        UpstoxHistoricalProvider
    )

    db = DatabaseConnection()

    candle_repository = CandleRepository(db)
    indicator_repository = IndicatorRepository(db)

    indicator_service = IndicatorService(
        candle_repository=candle_repository,
        indicator_repository=indicator_repository
    )

    start = datetime.fromisoformat(
        "2026-09-09T09:15:00+05:30"
    )

    end = datetime.fromisoformat(
        "2026-09-09T11:00:00+05:30"
    )

    # --------------------------------------------------
    # These are the 16 candles we actually backfilled.
    # --------------------------------------------------

    persist_timestamps = set(
        generate_expected_minutes(
            start_timestamp=start,
            end_timestamp=datetime.fromisoformat(
                "2026-09-09T09:30:00+05:30"
            )
        )
    )

    persist_timestamps.add(
        datetime.fromisoformat(
            "2026-09-09T10:02:00+05:30"
        )
    )

    # --------------------------------------------------
    # Fetch historical candles
    # --------------------------------------------------

    provider = UpstoxHistoricalProvider()

    raw_candles = provider.get_intraday_candles(
        instrument_key="NSE_EQ|INE002A01018",
        interval="1"
    )

    historical_candles = provider.convert_to_candles(
        instrument_id=2,
        candles=raw_candles
    )

    # --------------------------------------------------
    # Process ALL historical candles.
    # Persist only the original 16 timestamps.
    # --------------------------------------------------

    processed = (
        indicator_service
        .process_historical_candles(
            instrument_id=2,
            timeframe="1m",
            candles=historical_candles,
            start_timestamp=start,
            persist_timestamps=persist_timestamps
        )
    )

    print(
        f"Historical candles available: "
        f"{len(historical_candles)}"
    )

    print(
        f"Timestamps selected for persistence: "
        f"{len(persist_timestamps)}"
    )

    print(
        f"Indicators persisted: {processed}"
    )

    db.close()