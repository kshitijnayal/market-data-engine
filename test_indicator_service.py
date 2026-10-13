from database.connection import DatabaseConnection

from database.repository import (
    CandleRepository,
    IndicatorRepository
)

from market_data.candle import Candle

from market_data.indicator_service import (
    IndicatorService
)


def test_indicator_service():

    db = DatabaseConnection()

    candle_repository = CandleRepository(db)

    indicator_repository = IndicatorRepository(db)

    indicator_service = IndicatorService(
        candle_repository=candle_repository,
        indicator_repository=indicator_repository
    )

    instrument_id = 2
    timeframe = "1m"

    # ======================================================
    # INITIALIZE FROM HISTORICAL CANDLES
    # ======================================================

    initialized = indicator_service.initialize(
        instrument_id=instrument_id,
        timeframe=timeframe,
        limit=25
    )

    print()
    print(
        "Historical candles used for initialization:",
        initialized
    )

    assert initialized == 25

    # ======================================================
    # CREATE A NEW COMPLETED CANDLE
    # ======================================================

    rows = candle_repository.get_candles(
        instrument_id=instrument_id,
        timeframe=timeframe,
        limit=1
    )

    assert len(rows) == 1

    latest = rows[0]

    latest_timestamp = latest[2]

    # ------------------------------------------------------
    # Use a timestamp later than the latest historical candle
    # ------------------------------------------------------

    from datetime import timedelta

    new_timestamp = (
        latest_timestamp
        + timedelta(minutes=1)
    )

    new_candle = Candle(
        instrument_id=instrument_id,
        timestamp=new_timestamp,
        timeframe=timeframe,
        open_price=latest[7],
        high_price=latest[7],
        low_price=latest[7],
        close_price=latest[7],
        volume=latest[8]
    )

    # ======================================================
    # PROCESS LIVE-STYLE COMPLETED CANDLE
    # ======================================================

    values = indicator_service.process_candle(
        new_candle
    )

    print()
    print(
        "Processed new completed candle:"
    )

    print(
        "timestamp:",
        new_candle.timestamp
    )

    print(
        "EMA9:",
        values.ema_9
    )

    print(
        "EMA20:",
        values.ema_20
    )

    print(
        "EMA50:",
        values.ema_50
    )

    print(
        "RSI14:",
        values.rsi_14
    )

    print(
        "ATR14:",
        values.atr_14
    )

    print(
        "VolumeSMA20:",
        values.volume_sma_20
    )

    print(
        "VWAP:",
        values.vwap
    )

    # ======================================================
    # BASIC VALIDATION
    # ======================================================

    assert values.ema_9 is not None
    assert values.ema_20 is not None
    assert values.ema_50 is not None
    assert values.vwap is not None

    # ======================================================
    # VERIFY DATABASE PERSISTENCE
    # ======================================================

    latest_indicator = (
        indicator_repository.get_indicator(
            instrument_id=instrument_id,
            timestamp=new_timestamp,
            timeframe=timeframe
        )
    )

    assert latest_indicator is not None

    print()
    print(
        "Latest persisted indicator:"
    )

    print(
        latest_indicator
    )

    assert (
        latest_indicator[2]
        == new_timestamp
    )

    assert latest_indicator[5] is not None
    assert latest_indicator[6] is not None
    assert latest_indicator[7] is not None
    assert latest_indicator[8] is not None

    print()
    print(
        "PASS: indicator service initialization "
        "and live candle processing test"
    )

    db.close()


if __name__ == "__main__":

    test_indicator_service()