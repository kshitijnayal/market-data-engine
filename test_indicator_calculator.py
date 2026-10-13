from datetime import datetime, timedelta
from decimal import Decimal
from market_data.candle import Candle
from market_data.indicator_calculator import (
    IndicatorCalculator
)


# --------------------------------------------------
# Test helpers
# --------------------------------------------------

def create_candle(
    instrument_id: int,
    timestamp: datetime,
    close: float,
    volume: int
) -> Candle:

    return Candle(
        instrument_id=instrument_id,
        timestamp=timestamp,
        timeframe="1m",
        open_price=close - 1,
        high_price=close + 2,
        low_price=close - 2,
        close_price=close,
        volume=volume
    )


# --------------------------------------------------
# Main test
# --------------------------------------------------

def test_indicator_calculation():

    calculator = IndicatorCalculator()

    instrument_id = 1

    start_time = datetime(
        2026,
        8,
        27,
        9,
        15
    )

    results = []

    # --------------------------------------------------
    # Generate 30 deterministic candles
    # --------------------------------------------------

    for i in range(30):

        close = 100 + i

        candle = create_candle(
            instrument_id=instrument_id,
            timestamp=(
                start_time
                + timedelta(minutes=i)
            ),
            close=close,
            volume=100 + (i * 10)
        )

        values = calculator.calculate(
            candle
        )

        results.append(values)

    # --------------------------------------------------
    # EMA
    # --------------------------------------------------

    assert results[-1].ema_9 is not None
    assert results[-1].ema_20 is not None
    assert results[-1].ema_50 is not None

    # With continuously increasing prices,
    # shorter EMA should be above longer EMA.

    assert (
        results[-1].ema_9
        > results[-1].ema_20
    )

    assert (
        results[-1].ema_20
        > results[-1].ema_50
    )

    # --------------------------------------------------
    # RSI
    # --------------------------------------------------

    # After enough candles, RSI should exist.

    assert results[-1].rsi_14 is not None

    # Every price increased, therefore RSI
    # should be 100.

    assert (
        abs(
            results[-1].rsi_14 - Decimal("100")
        ) < Decimal("0.000001")
    )

    # --------------------------------------------------
    # ATR
    # --------------------------------------------------

    assert results[-1].atr_14 is not None

    assert (
        results[-1].atr_14 > 0
    )

    # --------------------------------------------------
    # Volume SMA
    # --------------------------------------------------

    assert (
        results[-1].volume_sma_20
        is not None
    )

    # Last 20 volumes:
    #
    # 200, 210, ..., 390
    #
    # Average = 295

    assert (
        abs(
            results[-1].volume_sma_20 - Decimal("295")
        ) < 0.000001
    )

    # --------------------------------------------------
    # VWAP
    # --------------------------------------------------

    assert (
        results[-1].vwap
        is not None
    )

    assert (
        results[-1].vwap > 0
    )

    # --------------------------------------------------
    # Print results
    # --------------------------------------------------

    print(
        "PASS: indicator calculation test"
    )

    print(
        f"EMA 9       : {results[-1].ema_9}"
    )

    print(
        f"EMA 20      : {results[-1].ema_20}"
    )

    print(
        f"EMA 50      : {results[-1].ema_50}"
    )

    print(
        f"RSI 14      : {results[-1].rsi_14}"
    )

    print(
        f"ATR 14      : {results[-1].atr_14}"
    )

    print(
        f"Volume SMA20: {results[-1].volume_sma_20}"
    )

    print(
        f"VWAP        : {results[-1].vwap}"
    )


# --------------------------------------------------
# Entry point
# --------------------------------------------------

if __name__ == "__main__":

    try:

        test_indicator_calculation()

    except AssertionError:

        print(
            "FAIL: indicator calculation test"
        )

        raise