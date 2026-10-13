from datetime import datetime, timedelta, timezone

from database.connection import DatabaseConnection

from database.repository import (
    CandleRepository,
    IndicatorRepository
)

from market_data.models import MarketTick
from market_data.candle_aggregator import CandleAggregator
from market_data.indicator_service import IndicatorService


def test_market_pipeline():

    db = DatabaseConnection()

    candle_repository = CandleRepository(db)

    indicator_repository = IndicatorRepository(db)

    # --------------------------------------------------
    # IndicatorService requires both repositories.
    # --------------------------------------------------

    indicator_service = IndicatorService(
        candle_repository=candle_repository,
        indicator_repository=indicator_repository
    )

    aggregator = CandleAggregator()

    instrument_id = 2

    start_time = datetime(
        2026,
        8,
        27,
        12,
        0,
        tzinfo=timezone.utc
    )

    # --------------------------------------------------
    # Generate synthetic ticks
    # --------------------------------------------------

    completed_candles = []

    volume = 1000

    for minute in range(25):

        base_time = (
            start_time
            + timedelta(minutes=minute)
        )

        for second in (5, 20, 40):

            timestamp = (
                base_time
                + timedelta(seconds=second)
            )

            price = (
                100.0
                + minute * 0.5
                + second * 0.01
            )

            volume += 10

            tick = MarketTick(
                instrument_id=instrument_id,
                timestamp=timestamp,
                last_price=price,
                last_quantity=10,
                volume=volume
            )

            candle = aggregator.process_tick(
                tick,
                timeframe="1m"
            )

            if candle is not None:

                completed_candles.append(
                    candle
                )

    # --------------------------------------------------
    # Flush final candle
    # --------------------------------------------------

    remaining = aggregator.flush()

    completed_candles.extend(
        remaining
    )

    print(
        "Candles generated:",
        len(completed_candles)
    )

    assert len(completed_candles) == 25

    # --------------------------------------------------
    # Persist candles + calculate indicators
    # --------------------------------------------------

    latest_values = None

    for candle in completed_candles:

        candle_repository.upsert_candle(
            candle
        )

        values = (
            indicator_service.process_candle(
                candle
            )
        )

        assert values is not None

        latest_values = values

    # --------------------------------------------------
    # Verify latest calculated indicators
    # --------------------------------------------------

    assert latest_values is not None

    assert latest_values.ema_9 is not None
    assert latest_values.ema_20 is not None
    assert latest_values.ema_50 is not None
    assert latest_values.rsi_14 is not None
    assert latest_values.atr_14 is not None
    assert latest_values.volume_sma_20 is not None
    assert latest_values.vwap is not None

    # --------------------------------------------------
    # Verify persisted indicators
    # --------------------------------------------------

    rows = indicator_repository.get_indicators(
        instrument_id=instrument_id,
        timeframe="1m",
        limit=25
    )

    print()
    print("Indicator rows:")
    print("----------------------------------------")

    for index, row in enumerate(rows, start=1):

        print(
            index,
            "| timestamp=",
            row[2],
            "| RSI=",
            row[4],
            "| EMA9=",
            row[5],
            "| ATR=",
            row[9],
            "| VolumeSMA20=",
            row[10]
        )

    print("----------------------------------------")
    print()

    assert len(rows) >= 1

    row = rows[0]

    # --------------------------------------------------
    # Verify latest row contains calculated indicators.
    # --------------------------------------------------

    assert row[1] == instrument_id
    assert row[3] == "1m"

    assert row[5] is not None       # EMA 9
    assert row[6] is not None       # EMA 20
    assert row[7] is not None       # EMA 50
    assert row[4] is not None       # RSI 14
    assert row[9] is not None       # ATR 14
    assert row[10] is not None      # Volume SMA 20
    assert row[8] is not None       # VWAP

    # --------------------------------------------------
    # PASS
    # --------------------------------------------------

    print(
        "PASS: complete market-data pipeline test"
    )

    print(
        "instrument_id:",
        instrument_id
    )

    print(
        "latest indicator row:",
        row
    )

    db.close()


if __name__ == "__main__":

    test_market_pipeline()