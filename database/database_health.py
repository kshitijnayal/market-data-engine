import logging
from typing import Any, Dict, List

from database.connection import DatabaseConnection


class DatabaseHealth:
    """
    Runs read-only data-quality checks against the ExaFinvest
    PostgreSQL market database.

    The health layer does not modify database data. It is intended
    to answer one question:

        "Can this database currently be trusted for analysis?"

    Checks include:
        - Required table presence
        - Row counts
        - Foreign-key orphan records
        - Duplicate logical records
        - Invalid OHLC values
        - Invalid volume / quantity values
        - Invalid bid/ask relationships
        - Missing critical candle data
        - Invalid timeframes
        - Indicator records without a matching candle
    """

    REQUIRED_TABLES = (
        "instruments",
        "ticks",
        "candles",
        "indicators",
    )

    VALID_TIMEFRAMES = (
        "1m",
        "5m",
        "15m",
        "30m",
        "1h",
        "1d",
    )

    def __init__(self, db: DatabaseConnection) -> None:
        self.db = db
        self.logger = logging.getLogger(self.__class__.__name__)

    def _fetch_one(self, query: str) -> Any:
        connection = self.db.connect()

        with connection.cursor() as cursor:
            cursor.execute(query)
            row = cursor.fetchone()

        return row[0] if row else 0

    def _fetch_rows(self, query: str) -> List[Any]:
        connection = self.db.connect()

        with connection.cursor() as cursor:
            cursor.execute(query)
            return cursor.fetchall()

    def check_tables(self) -> Dict[str, Any]:
        """Verify that all required market-data tables exist."""

        rows = self._fetch_rows(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = ANY(
                    ARRAY[
                        'instruments',
                        'ticks',
                        'candles',
                        'indicators'
                    ]
              )
            ORDER BY table_name;
            """
        )

        found = {row[0] for row in rows}
        missing = [
            table
            for table in self.REQUIRED_TABLES
            if table not in found
        ]

        return {
            "found": sorted(found),
            "missing": missing,
            "ok": not missing,
        }

    def get_row_counts(self) -> Dict[str, int]:
        """Return current row counts for all core tables."""

        return {
            "instruments": self._fetch_one(
                "SELECT COUNT(*) FROM instruments;"
            ),
            "ticks": self._fetch_one(
                "SELECT COUNT(*) FROM ticks;"
            ),
            "candles": self._fetch_one(
                "SELECT COUNT(*) FROM candles;"
            ),
            "indicators": self._fetch_one(
                "SELECT COUNT(*) FROM indicators;"
            ),
        }

    def check_instrument_integrity(self) -> Dict[str, int]:
        """Check active/inactive instruments and duplicate identities."""

        inactive = self._fetch_one(
            """
            SELECT COUNT(*)
            FROM instruments
            WHERE active = FALSE;
            """
        )

        duplicate_symbols = self._fetch_one(
            """
            SELECT COUNT(*)
            FROM (
                SELECT symbol, exchange
                FROM instruments
                GROUP BY symbol, exchange
                HAVING COUNT(*) > 1
            ) AS duplicates;
            """
        )

        duplicate_provider_ids = self._fetch_one(
            """
            SELECT COUNT(*)
            FROM (
                SELECT provider, provider_instrument_id
                FROM instruments
                WHERE provider IS NOT NULL
                  AND provider_instrument_id IS NOT NULL
                GROUP BY provider, provider_instrument_id
                HAVING COUNT(*) > 1
            ) AS duplicates;
            """
        )

        return {
            "inactive_instruments": inactive,
            "duplicate_symbol_exchange_groups": duplicate_symbols,
            "duplicate_provider_id_groups": duplicate_provider_ids,
        }

    def check_orphans(self) -> Dict[str, int]:
        """Find records whose instrument no longer exists."""

        orphan_ticks = self._fetch_one(
            """
            SELECT COUNT(*)
            FROM ticks t
            LEFT JOIN instruments i
                ON i.instrument_id = t.instrument_id
            WHERE i.instrument_id IS NULL;
            """
        )

        orphan_candles = self._fetch_one(
            """
            SELECT COUNT(*)
            FROM candles c
            LEFT JOIN instruments i
                ON i.instrument_id = c.instrument_id
            WHERE i.instrument_id IS NULL;
            """
        )

        orphan_indicators = self._fetch_one(
            """
            SELECT COUNT(*)
            FROM indicators ind
            LEFT JOIN instruments i
                ON i.instrument_id = ind.instrument_id
            WHERE i.instrument_id IS NULL;
            """
        )

        return {
            "orphan_ticks": orphan_ticks,
            "orphan_candles": orphan_candles,
            "orphan_indicators": orphan_indicators,
        }

    def check_duplicates(self) -> Dict[str, int]:
        """Check logical uniqueness of candles and indicators."""

        duplicate_candles = self._fetch_one(
            """
            SELECT COUNT(*)
            FROM (
                SELECT instrument_id, timestamp, timeframe
                FROM candles
                GROUP BY instrument_id, timestamp, timeframe
                HAVING COUNT(*) > 1
            ) AS duplicates;
            """
        )

        duplicate_indicators = self._fetch_one(
            """
            SELECT COUNT(*)
            FROM (
                SELECT instrument_id, timestamp, timeframe
                FROM indicators
                GROUP BY instrument_id, timestamp, timeframe
                HAVING COUNT(*) > 1
            ) AS duplicates;
            """
        )

        return {
            "duplicate_candle_groups": duplicate_candles,
            "duplicate_indicator_groups": duplicate_indicators,
        }

    def check_ohlc_integrity(self) -> Dict[str, int]:
        """
        Check OHLC relationships.

        A valid OHLC record must satisfy:

            high >= open
            high >= close
            high >= low
            low <= open
            low <= close

        Null OHLC values are handled separately.
        """

        invalid_candles = self._fetch_one(
            """
            SELECT COUNT(*)
            FROM candles
            WHERE open_price IS NOT NULL
              AND high_price IS NOT NULL
              AND low_price IS NOT NULL
              AND close_price IS NOT NULL
              AND (
                    high_price < open_price
                 OR high_price < close_price
                 OR high_price < low_price
                 OR low_price > open_price
                 OR low_price > close_price
              );
            """
        )

        missing_candle_ohlc = self._fetch_one(
            """
            SELECT COUNT(*)
            FROM candles
            WHERE open_price IS NULL
               OR high_price IS NULL
               OR low_price IS NULL
               OR close_price IS NULL;
            """
        )

        invalid_ticks = self._fetch_one(
            """
            SELECT COUNT(*)
            FROM ticks
            WHERE last_price IS NOT NULL
              AND last_price < 0;
            """
        )

        return {
            "invalid_candle_ohlc": invalid_candles,
            "candles_missing_ohlc": missing_candle_ohlc,
            "invalid_tick_price_records": invalid_ticks,
        }

    def check_quantity_integrity(self) -> Dict[str, int]:
        """Check that quantities and volumes are not negative."""

        negative_tick_quantity = self._fetch_one(
            """
            SELECT COUNT(*)
            FROM ticks
            WHERE last_quantity IS NOT NULL
              AND last_quantity < 0;
            """
        )

        negative_tick_volume = self._fetch_one(
            """
            SELECT COUNT(*)
            FROM ticks
            WHERE volume IS NOT NULL
              AND volume < 0;
            """
        )

        negative_candle_volume = self._fetch_one(
            """
            SELECT COUNT(*)
            FROM candles
            WHERE volume IS NOT NULL
              AND volume < 0;
            """
        )

        return {
            "negative_tick_quantity": negative_tick_quantity,
            "negative_tick_volume": negative_tick_volume,
            "negative_candle_volume": negative_candle_volume,
        }

    def check_bid_ask_integrity(self) -> Dict[str, int]:
        """Check that bid price does not exceed ask price."""

        invalid_bid_ask = self._fetch_one(
            """
            SELECT COUNT(*)
            FROM ticks
            WHERE bid_price IS NOT NULL
              AND ask_price IS NOT NULL
              AND bid_price > ask_price;
            """
        )

        return {
            "invalid_bid_ask_records": invalid_bid_ask,
        }

    def check_timeframes(self) -> Dict[str, int]:
        """Find candle/indicator records using unsupported timeframes."""

        invalid_candle_timeframes = self._fetch_one(
            """
            SELECT COUNT(*)
            FROM candles
            WHERE timeframe <> ALL(
                ARRAY['1m', '5m', '15m', '30m', '1h', '1d']
            );
            """
        )

        invalid_indicator_timeframes = self._fetch_one(
            """
            SELECT COUNT(*)
            FROM indicators
            WHERE timeframe <> ALL(
                ARRAY['1m', '5m', '15m', '30m', '1h', '1d']
            );
            """
        )

        return {
            "invalid_candle_timeframes": invalid_candle_timeframes,
            "invalid_indicator_timeframes": invalid_indicator_timeframes,
        }

    def check_indicator_coverage(self) -> Dict[str, int]:
        """
        Find indicators that do not have a matching candle.

        This is reported separately because indicator and candle
        timestamps may legitimately differ while the ingestion
        pipeline is being evolved. It is therefore a warning rather
        than an automatic database failure.
        """

        indicators_without_candle = self._fetch_one(
            """
            SELECT COUNT(*)
            FROM indicators ind
            LEFT JOIN candles c
                ON c.instrument_id = ind.instrument_id
               AND c.timestamp = ind.timestamp
               AND c.timeframe = ind.timeframe
            WHERE c.candle_id IS NULL;
            """
        )

        return {
            "indicators_without_matching_candle":
                indicators_without_candle,
        }

    def run(self) -> Dict[str, Any]:
        """
        Run all database health checks.

        Returns a dictionary containing:
            - status: HEALTHY / WARNING / ERROR
            - row counts
            - individual check results
        """

        try:
            table_check = self.check_tables()

            if not table_check["ok"]:
                return {
                    "status": "ERROR",
                    "tables": table_check,
                    "error": "Required database tables are missing.",
                }

            checks = {
                "tables": table_check,
                "row_counts": self.get_row_counts(),
                "instrument_integrity":
                    self.check_instrument_integrity(),
                "orphans": self.check_orphans(),
                "duplicates": self.check_duplicates(),
                "ohlc_integrity": self.check_ohlc_integrity(),
                "quantity_integrity":
                    self.check_quantity_integrity(),
                "bid_ask_integrity":
                    self.check_bid_ask_integrity(),
                "timeframes": self.check_timeframes(),
                "indicator_coverage":
                    self.check_indicator_coverage(),
            }

            errors = []

            zero_required = (
                "orphan_ticks",
                "orphan_candles",
                "orphan_indicators",
                "duplicate_candle_groups",
                "duplicate_indicator_groups",
                "invalid_candle_ohlc",
                "candles_missing_ohlc",
                "invalid_tick_price_records",
                "negative_tick_quantity",
                "negative_tick_volume",
                "negative_candle_volume",
                "invalid_bid_ask_records",
                "invalid_candle_timeframes",
                "invalid_indicator_timeframes",
            )

            for section in checks.values():
                if not isinstance(section, dict):
                    continue

                for key in zero_required:
                    if key in section and section[key] > 0:
                        errors.append(
                            f"{key}={section[key]}"
                        )

            warning_count = (
                checks["indicator_coverage"]
                ["indicators_without_matching_candle"]
            )

            if errors:
                status = "ERROR"
            elif warning_count > 0:
                status = "WARNING"
            else:
                status = "HEALTHY"

            return {
                "status": status,
                "checks": checks,
                "errors": errors,
            }

        except Exception:
            self.logger.exception(
                "Database health check failed."
            )
            raise

    def print_report(self, report: Dict[str, Any]) -> None:
        """Print a human-readable database health report."""

        print()
        print("=" * 60)
        print("EXAFINVEST DATABASE HEALTH")
        print("=" * 60)

        print()
        print("TABLES")

        tables = report.get("tables", {})

        print(
            "  Required tables:",
            ", ".join(self.REQUIRED_TABLES)
        )

        if tables.get("missing"):
            print(
                "  Missing:",
                ", ".join(tables["missing"])
            )
        else:
            print("  Status: OK")

        checks = report.get("checks", {})

        print()
        print("ROW COUNTS")

        for table, count in checks.get(
            "row_counts", {}
        ).items():
            print(
                f"  {table:<12}: {count:,}"
            )

        print()
        print("DATA INTEGRITY")

        sections = (
            "instrument_integrity",
            "orphans",
            "duplicates",
            "ohlc_integrity",
            "quantity_integrity",
            "bid_ask_integrity",
            "timeframes",
            "indicator_coverage",
        )

        for section_name in sections:

            values = checks.get(section_name, {})

            if not values:
                continue

            print()
            print(f"  {section_name.replace('_', ' ').title()}")

            for key, value in values.items():
                print(
                    f"    {key}: {value:,}"
                )

        print()
        print("=" * 60)
        print(
            f"OVERALL STATUS: {report.get('status', 'UNKNOWN')}"
        )
        print("=" * 60)
        print()

        if report.get("errors"):
            print("ERRORS:")
            for error in report["errors"]:
                print(f"  - {error}")
            print()
