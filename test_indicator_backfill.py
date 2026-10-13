from database.connection import DatabaseConnection
from database.repository import (
    CandleRepository,
    IndicatorRepository
)

from market_data.indicator_backfill_service import (
    IndicatorBackfillService
)


def test_indicator_backfill():

    db = DatabaseConnection()

    candle_repository = CandleRepository(db)

    indicator_repository = IndicatorRepository(db)

    backfill_service = IndicatorBackfillService(
        candle_repository=candle_repository,
        indicator_repository=indicator_repository
    )

    instrument_id = 2

    # --------------------------------------------------
    # Run backfill
    # --------------------------------------------------

    processed = backfill_service.backfill(
        instrument_id=instrument_id,
        timeframe="1m",
        limit=25
    )

    print()
    print(
        "Candles processed:",
        processed
    )

    assert processed == 25

    # --------------------------------------------------
    # Read indicators
    # --------------------------------------------------

    rows = indicator_repository.get_indicators(
        instrument_id=instrument_id,
        timeframe="1m",
        limit=25
    )

    print()
    print("Backfilled indicator rows:")
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
            "| EMA20=",
            row[6],
            "| EMA50=",
            row[7],
            "| VWAP=",
            row[8],
            "| ATR=",
            row[9],
            "| VolumeSMA20=",
            row[10]
        )

    print("----------------------------------------")
    print()

    # --------------------------------------------------
    # Basic verification
    # --------------------------------------------------

    assert len(rows) == 25

    latest = rows[0]

    assert latest[5] is not None
    assert latest[6] is not None
    assert latest[7] is not None
    assert latest[8] is not None

    print(
        "PASS: indicator historical backfill test"
    )

    print(
        "instrument_id:",
        instrument_id
    )

    print(
        "latest indicator row:",
        latest
    )

    db.close()


if __name__ == "__main__":

    test_indicator_backfill()