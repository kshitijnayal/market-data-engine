from datetime import datetime, timezone

from market_data.candle_aggregator import CandleAggregator
from market_data.models import MarketTick


def make_tick(
    timestamp: str,
    price: float,
    volume: int
) -> MarketTick:

    return MarketTick(
        instrument_id=1,
        timestamp=datetime.fromisoformat(
            timestamp
        ).replace(tzinfo=timezone.utc),
        last_price=price,
        volume=volume
    )


def test_one_minute_candle():

    aggregator = CandleAggregator()

    candle = aggregator.process_tick(
        make_tick(
            "2026-08-27T09:15:05",
            100.0,
            1000
        )
    )

    assert candle is None

    candle = aggregator.process_tick(
        make_tick(
            "2026-08-27T09:15:20",
            101.0,
            1025
        )
    )

    assert candle is None

    candle = aggregator.process_tick(
        make_tick(
            "2026-08-27T09:15:45",
            99.0,
            1060
        )
    )

    assert candle is None

    # Tick in the next minute closes 09:15 candle.
    candle = aggregator.process_tick(
        make_tick(
            "2026-08-27T09:16:02",
            100.0,
            1080
        )
    )

    assert candle is not None

    assert candle.instrument_id == 1
    assert candle.timeframe == "1m"

    assert candle.open_price == 100.0
    assert candle.high_price == 101.0
    assert candle.low_price == 99.0
    assert candle.close_price == 99.0

    assert candle.volume == 60

if __name__ == "__main__":
    test_one_minute_candle()
    print("PASS: one-minute candle aggregation test")