from datetime import datetime, timezone

from database.connection import DatabaseConnection
from database.repository import IndicatorRepository
from market_data.indicator_calculator import IndicatorValues


def test_indicator_repository():

    db = DatabaseConnection()

    repository = IndicatorRepository(db)

    # --------------------------------------------------
    # Get a real active instrument
    # --------------------------------------------------

    connection = db.connect()
    cursor = connection.cursor()

    try:

        cursor.execute("""
            SELECT instrument_id
            FROM instruments
            WHERE active = TRUE
            ORDER BY instrument_id
            LIMIT 1
        """)

        row = cursor.fetchone()

    finally:

        cursor.close()

    if row is None:

        raise RuntimeError(
            "No active instrument found for indicator repository test."
        )

    instrument_id = row[0]

    # --------------------------------------------------
    # Indicator values
    # --------------------------------------------------

    values = IndicatorValues(
        rsi_14=55.5,
        ema_9=101.0,
        ema_20=100.5,
        ema_50=99.5,
        vwap=100.25,
        atr_14=2.5,
        volume_sma_20=1500.0
    )

    # --------------------------------------------------
    # Insert indicator
    # --------------------------------------------------

    indicator_id = repository.upsert_indicators(
        instrument_id=instrument_id,
        timestamp=datetime.now(timezone.utc),
        timeframe="1m",
        values=values
    )

    assert indicator_id is not None

    # --------------------------------------------------
    # Read it back
    # --------------------------------------------------

    rows = repository.get_indicators(
        instrument_id=instrument_id,
        timeframe="1m",
        limit=1
    )

    assert len(rows) == 1

    row = rows[0]

    # --------------------------------------------------
    # Validate persisted values
    # --------------------------------------------------

    assert row[1] == instrument_id
    assert row[3] == "1m"

    assert float(row[4]) == 55.5
    assert float(row[5]) == 101.0
    assert float(row[6]) == 100.5
    assert float(row[7]) == 99.5
    assert float(row[8]) == 100.25
    assert float(row[9]) == 2.5
    assert float(row[10]) == 1500.0

    print(
        "PASS: indicator repository test"
    )

    print(
        "instrument_id:",
        instrument_id
    )

    print(
        "indicator_id:",
        indicator_id
    )

    db.close()


if __name__ == "__main__":

    test_indicator_repository()