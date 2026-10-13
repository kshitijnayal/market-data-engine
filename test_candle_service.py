from datetime import datetime, timedelta
from decimal import Decimal

from database.connection import DatabaseConnection
from database.repository import (
    CandleRepository,
    IndicatorRepository
)

from market_data.models import MarketTick
from market_data.candle_service import CandleService


def test_candle_service():

    db = DatabaseConnection()

    candle_repository = CandleRepository(db)

    indicator_repository = IndicatorRepository(db)

    candle_service = CandleService(
        candle_repository=candle_repository,
        indicator_repository=indicator_repository
    )

    instrument_id = 2
    timeframe = "1m"

    # --------------------------------------------------
    # Test timestamps
    # --------------------------------------------------

    start = datetime.fromisoformat(
        "2026-08-28T10:00:10+05:30"
    )

    timestamps = [
        start,
        start + timedelta(seconds=10),
        start + timedelta(seconds=30),
        start + timedelta(seconds=49),
        start + timedelta(seconds=65),
    ]

    prices = [
        Decimal("100.00"),
        Decimal("101.00"),
        Decimal("99.00"),
        Decimal("102.00"),
        Decimal("103.00"),
    ]

    cumulative_volumes = [
        1000,
        1010,
        1030,
        1050,
        1070,
    ]

    # --------------------------------------------------
    # Expected completed candle
    # --------------------------------------------------

    expected_candle_timestamp = (
        start.replace(
            second=0,
            microsecond=0
        )
    )

    # --------------------------------------------------
    # Process ticks
    # --------------------------------------------------

    completed_indicators = []

    for timestamp, price, volume in zip(
        timestamps,
        prices,
        cumulative_volumes
    ):

        tick = MarketTick(
            instrument_id=instrument_id,
            timestamp=timestamp,
            last_price=price,
            last_quantity=10,
            volume=volume,
            bid_price=price,
            ask_price=price,
            open_price=price,
            high_price=price,
            low_price=price,
            previous_close=Decimal("99.00")
        )

        result = candle_service.process_tick(
            tick=tick,
            timeframe=timeframe
        )

        if result is not None:

            completed_indicators.append(
                result
            )

    # --------------------------------------------------
    # Verify completed candle was detected
    #
    # First four ticks:
    #
    # 10:00:10
    # 10:00:20
    # 10:00:40
    # 10:00:59
    #
    # Fifth tick:
    #
    # 10:01:15
    #
    # Therefore the 10:00 candle completes.
    # --------------------------------------------------

    assert len(completed_indicators) == 1

    indicators = completed_indicators[0]

    print()
    print("Completed candle detected")
    print("----------------------------------------")

    print(
        "EMA9:",
        indicators.ema_9
    )

    print(
        "EMA20:",
        indicators.ema_20
    )

    print(
        "EMA50:",
        indicators.ema_50
    )

    print(
        "RSI14:",
        indicators.rsi_14
    )

    print(
        "ATR14:",
        indicators.atr_14
    )

    print(
        "VolumeSMA20:",
        indicators.volume_sma_20
    )

    print(
        "VWAP:",
        indicators.vwap
    )

    print("----------------------------------------")

    # --------------------------------------------------
    # Verify persisted candle
    # --------------------------------------------------

    candles = candle_repository.get_candles(
        instrument_id=instrument_id,
        timeframe=timeframe,
        limit=10
    )

    print()
    print("Persisted candles:")
    print("----------------------------------------")

    for row in candles:

        print(
            row
        )

    print("----------------------------------------")

    assert len(candles) >= 1

    # --------------------------------------------------
    # Find the candle created by this test
    #
    # Do not assume candles[0] is our test candle because
    # the database may already contain newer candles.
    # --------------------------------------------------

    matching_candles = [
        row
        for row in candles
        if (
            row[1] == instrument_id
            and row[2] == expected_candle_timestamp
            and row[3] == timeframe
        )
    ]

    assert len(matching_candles) == 1

    latest_candle = matching_candles[0]

    # --------------------------------------------------
    # Candle identity
    # --------------------------------------------------

    assert latest_candle[1] == instrument_id

    assert latest_candle[2] == (
        expected_candle_timestamp
    )

    assert latest_candle[3] == timeframe

    # --------------------------------------------------
    # Verify OHLC
    #
    # Ticks:
    #
    # 100
    # 101
    # 99
    # 102
    #
    # Therefore:
    #
    # Open  = 100
    # High  = 102
    # Low   = 99
    # Close = 102
    # --------------------------------------------------

    assert latest_candle[4] == Decimal("100.00")

    assert latest_candle[5] == Decimal("102.00")

    assert latest_candle[6] == Decimal("99.00")

    assert latest_candle[7] == Decimal("102.00")

    # --------------------------------------------------
    # Verify candle volume
    #
    # Provider volume is cumulative.
    #
    # First tick:
    #   1000 -> delta 0
    #
    # Second:
    #   1010 - 1000 = 10
    #
    # Third:
    #   1030 - 1010 = 20
    #
    # Fourth:
    #   1050 - 1030 = 20
    #
    # Total:
    #   0 + 10 + 20 + 20 = 50
    # --------------------------------------------------

    assert latest_candle[8] == 50

    # --------------------------------------------------
    # Verify persisted indicator
    # --------------------------------------------------

    indicator = (
        indicator_repository.get_indicator(
            instrument_id=instrument_id,
            timestamp=expected_candle_timestamp,
            timeframe=timeframe
        )
    )

    print()
    print("Persisted indicator:")
    print("----------------------------------------")

    print(
        indicator
    )

    print("----------------------------------------")

    # --------------------------------------------------
    # Indicator must exist
    # --------------------------------------------------

    assert indicator is not None

    # --------------------------------------------------
    # Verify indicator identity
    #
    # The exact tuple layout depends on the repository,
    # but based on the current indicators SELECT structure:
    #
    # [0] indicator_id
    # [1] instrument_id
    # [2] timestamp
    # [3] timeframe
    # [4] RSI14
    # [5] EMA9
    # [6] EMA20
    # [7] EMA50
    # [8] VWAP
    # [9] ATR14
    # [10] VolumeSMA20
    # --------------------------------------------------

    assert indicator[1] == instrument_id

    assert indicator[2] == (
        expected_candle_timestamp
    )

    assert indicator[3] == timeframe

    # --------------------------------------------------
    # Basic indicator verification
    #
    # Only one completed candle has been sent through
    # this CandleService instance.
    #
    # Therefore:
    #
    # EMA9   -> available
    # EMA20  -> available
    # EMA50  -> available
    # VWAP   -> available
    #
    # RSI14, ATR14 and VolumeSMA20 remain in warm-up.
    # --------------------------------------------------

    assert indicator[5] is not None

    assert indicator[6] is not None

    assert indicator[7] is not None

    assert indicator[8] is not None

    assert indicator[4] is None

    assert indicator[9] is None

    assert indicator[10] is None

    # --------------------------------------------------
    # Verify returned values match persisted values
    # --------------------------------------------------

    assert (
        indicator[5]
        == indicators.ema_9
    )

    assert (
        indicator[6]
        == indicators.ema_20
    )

    assert (
        indicator[7]
        == indicators.ema_50
    )

    assert (
        indicator[8]
        == indicators.vwap
    )

    assert (
        indicator[9]
        == indicators.atr_14
    )

    assert (
        indicator[10]
        == indicators.volume_sma_20
    )

    # --------------------------------------------------
    # Success
    # --------------------------------------------------

    print()
    print(
        "PASS: candle service integration test"
    )

    print(
        "instrument_id:",
        instrument_id
    )

    print(
        "completed candle:",
        latest_candle
    )

    print(
        "persisted indicator:",
        indicator
    )

    db.close()


if __name__ == "__main__":

    test_candle_service()