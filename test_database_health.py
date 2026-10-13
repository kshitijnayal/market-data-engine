from database.connection import DatabaseConnection
from database.database_health import DatabaseHealth


def test_database_health():

    db = DatabaseConnection()

    try:

        health = DatabaseHealth(db)

        report = health.run()

        health.print_report(report)

        # ======================================================
        # REQUIRED TABLES
        # ======================================================

        tables = report["checks"]["tables"]

        assert tables["ok"] is True

        # ======================================================
        # DATA INTEGRITY
        # ======================================================

        checks = report["checks"]

        instrument_integrity = checks["instrument_integrity"]

        assert (
            instrument_integrity["duplicate_symbol_exchange_groups"]
            == 0
        )

        assert (
            instrument_integrity["duplicate_provider_id_groups"]
            == 0
        )

        orphans = checks["orphans"]

        assert orphans["orphan_ticks"] == 0
        assert orphans["orphan_candles"] == 0
        assert orphans["orphan_indicators"] == 0

        duplicates = checks["duplicates"]

        assert duplicates["duplicate_candle_groups"] == 0
        assert duplicates["duplicate_indicator_groups"] == 0

        ohlc = checks["ohlc_integrity"]

        assert ohlc["invalid_candle_ohlc"] == 0
        assert ohlc["candles_missing_ohlc"] == 0
        assert ohlc["invalid_tick_price_records"] == 0

        quantity = checks["quantity_integrity"]

        assert quantity["negative_tick_quantity"] == 0
        assert quantity["negative_tick_volume"] == 0
        assert quantity["negative_candle_volume"] == 0

        bid_ask = checks["bid_ask_integrity"]

        assert bid_ask["invalid_bid_ask_records"] == 0

        timeframes = checks["timeframes"]

        assert timeframes["invalid_candle_timeframes"] == 0
        assert timeframes["invalid_indicator_timeframes"] == 0

        # ======================================================
        # INDICATOR COVERAGE
        # ======================================================

        coverage = checks["indicator_coverage"]

        print()
        print(
            "Indicator coverage warning:",
            coverage["indicators_without_matching_candle"]
        )

        print()
        print(
            "PASS: database structural and integrity checks"
        )

    finally:

        db.close()


if __name__ == "__main__":

    test_database_health()