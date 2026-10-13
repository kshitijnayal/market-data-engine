from database.connection import DatabaseConnection
from database.repository import (
    CandleRepository,
    IndicatorRepository,
    TickRepository
)

from market_data.market_data_service import (
    MarketDataService
)

from market_data.test_provider import (
    TestMarketDataProvider
)


def test_market_data_service():

    # ======================================================
    # USE EXISTING VALID INSTRUMENT
    # ======================================================

    instrument_id = 7
    timeframe = "1m"

    # ======================================================
    # CREATE TEST PROVIDER
    # ======================================================

    provider = TestMarketDataProvider()

    # ======================================================
    # CREATE MARKET DATA SERVICE
    # ======================================================

    service = MarketDataService(
        provider=provider
    )

    # ======================================================
    # START SERVICE
    # ======================================================

    service.start()

    try:

        # ==================================================
        # SEND SYNTHETIC TICK
        # ==================================================

        provider.subscribe(
            [
                str(instrument_id)
            ]
        )

        # ==================================================
        # VERIFY TICK WAS RECEIVED
        # ==================================================

        assert (
            service._total_ticks_received
            == 1
        )

        # ==================================================
        # STOP SERVICE
        #
        # stop() flushes the remaining tick buffer.
        # ==================================================

    finally:

        service.stop()

    # ======================================================
    # VERIFY TICK PERSISTENCE
    # ======================================================

    db = DatabaseConnection()

    tick_repository = TickRepository(db)

    tick_count = (
        tick_repository.count_ticks()
    )

    print()
    print(
        "Total ticks in database:",
        tick_count
    )

    assert tick_count > 0

    # ======================================================
    # VERIFY CANDLE DATA
    # ======================================================

    candle_repository = CandleRepository(db)

    candles = (
        candle_repository.get_candles(
            instrument_id=instrument_id,
            timeframe=timeframe,
            limit=10
        )
    )

    print()
    print(
        "Candles found:",
        len(candles)
    )

    assert len(candles) > 0

    # ======================================================
    # VERIFY INDICATOR DATA
    # ======================================================

    indicator_repository = IndicatorRepository(db)

    indicators = (
        indicator_repository.get_indicators(
            instrument_id=instrument_id,
            timeframe=timeframe,
            limit=10
        )
    )

    print()
    print(
        "Indicators found:",
        len(indicators)
    )

    assert len(indicators) > 0

    # ======================================================
    # CLOSE DATABASE
    # ======================================================

    db.close()

    print()
    print(
        "PASS: market data service integration test"
    )


if __name__ == "__main__":

    test_market_data_service()