import logging
from typing import List

from psycopg2.extras import execute_values

from market_data.models import MarketTick
from database.connection import DatabaseConnection


# --------------------------------------------------
# Tick Repository
# --------------------------------------------------

class TickRepository:
    """
    Handles persistence of market ticks into PostgreSQL.

    A canonical tick is identified by:

        instrument_id
        timestamp
        last_price
        last_quantity
        volume

    Upstox full-feed updates can repeat the same trade state
    while bid/ask quotes change. Those updates are treated as
    successive snapshots of the same canonical tick.
    """

    def __init__(
        self,
        db: DatabaseConnection
    ):

        self.db = db

        self.logger = logging.getLogger(
            self.__class__.__name__
        )

    def save_ticks(
        self,
        ticks: List[MarketTick]
    ) -> int:

        if not ticks:
            return 0

        # --------------------------------------------------
        # Canonicalize the incoming batch
        # --------------------------------------------------
        #
        # Keep only the last received snapshot for each
        # canonical trade state.
        #
        # NULL-volume ticks are deliberately not persisted.
        # They can still continue through the candle pipeline
        # because MarketDataService processes the tick separately.
        # --------------------------------------------------

        canonical_ticks = {}

        null_volume_count = 0

        for tick in ticks:

            if tick.volume is None:

                null_volume_count += 1

                continue

            key = (
                tick.instrument_id,
                tick.timestamp,
                tick.last_price,
                tick.last_quantity,
                tick.volume
            )

            canonical_ticks[key] = tick

        if null_volume_count:

            self.logger.warning(
                "Skipped %s tick(s) with NULL volume "
                "from raw tick persistence.",
                null_volume_count
            )

        if not canonical_ticks:
            return 0

        values = [
            (
                tick.instrument_id,
                tick.timestamp,
                tick.last_price,
                tick.last_quantity,
                tick.volume,
                tick.bid_price,
                tick.ask_price,
                tick.open_price,
                tick.high_price,
                tick.low_price,
                tick.previous_close
            )
            for tick in canonical_ticks.values()
        ]

        connection = self.db.connect()
        cursor = connection.cursor()

        try:

            # --------------------------------------------------
            # Update an existing canonical tick
            # --------------------------------------------------
            #
            # Incoming quote fields are explicitly cast to
            # numeric because execute_values can otherwise infer
            # VALUES columns as text when Python strings are used.
            #
            # COALESCE prevents a later snapshot with a missing
            # quote from erasing an already known non-null quote.
            # --------------------------------------------------

            update_query = """
                UPDATE ticks AS t
                SET
                    bid_price = COALESCE(
                        v.bid_price::numeric,
                        t.bid_price
                    ),
                    ask_price = COALESCE(
                        v.ask_price::numeric,
                        t.ask_price
                    ),
                    open_price = COALESCE(
                        v.open_price::numeric,
                        t.open_price
                    ),
                    high_price = COALESCE(
                        v.high_price::numeric,
                        t.high_price
                    ),
                    low_price = COALESCE(
                        v.low_price::numeric,
                        t.low_price
                    ),
                    previous_close = COALESCE(
                        v.previous_close::numeric,
                        t.previous_close
                    )
                FROM (
                    VALUES %s
                ) AS v (
                    instrument_id,
                    timestamp,
                    last_price,
                    last_quantity,
                    volume,
                    bid_price,
                    ask_price,
                    open_price,
                    high_price,
                    low_price,
                    previous_close
                )
                WHERE t.instrument_id = v.instrument_id
                  AND t.timestamp IS NOT DISTINCT FROM v.timestamp
                  AND t.last_price IS NOT DISTINCT FROM v.last_price
                  AND t.last_quantity IS NOT DISTINCT FROM v.last_quantity
                  AND t.volume IS NOT DISTINCT FROM v.volume
                  AND (
                      t.bid_price IS DISTINCT FROM
                          COALESCE(
                              v.bid_price::numeric,
                              t.bid_price
                          )
                      OR
                      t.ask_price IS DISTINCT FROM
                          COALESCE(
                              v.ask_price::numeric,
                              t.ask_price
                          )
                      OR
                      t.open_price IS DISTINCT FROM
                          COALESCE(
                              v.open_price::numeric,
                              t.open_price
                          )
                      OR
                      t.high_price IS DISTINCT FROM
                          COALESCE(
                              v.high_price::numeric,
                              t.high_price
                          )
                      OR
                      t.low_price IS DISTINCT FROM
                          COALESCE(
                              v.low_price::numeric,
                              t.low_price
                          )
                      OR
                      t.previous_close IS DISTINCT FROM
                          COALESCE(
                              v.previous_close::numeric,
                              t.previous_close
                          )
                  )
            """

            execute_values(
                cursor,
                update_query,
                values,
                template=(
                    "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                ),
                page_size=250
            )

            # --------------------------------------------------
            # Insert genuinely new canonical ticks
            # --------------------------------------------------

            insert_query = """
                INSERT INTO ticks (
                    instrument_id,
                    timestamp,
                    last_price,
                    last_quantity,
                    volume,
                    bid_price,
                    ask_price,
                    open_price,
                    high_price,
                    low_price,
                    previous_close
                )
                VALUES %s
                ON CONFLICT (
                    instrument_id,
                    timestamp,
                    last_price,
                    last_quantity,
                    volume
                )
                DO NOTHING
            """

            execute_values(
                cursor,
                insert_query,
                values,
                template=(
                    "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                ),
                page_size=250
            )

            inserted = cursor.rowcount

            connection.commit()

            return inserted

        except Exception:

            connection.rollback()

            raise

        finally:

            cursor.close()

    def count_ticks(self) -> int:

        connection = self.db.connect()

        query = """
            SELECT COUNT(*)
            FROM ticks
        """

        cursor = connection.cursor()

        try:

            cursor.execute(query)

            result = cursor.fetchone()

            return result[0]

        finally:

            cursor.close()


# --------------------------------------------------
# Candle Repository
# --------------------------------------------------

class CandleRepository:
    """
    Handles persistence of OHLCV candles into PostgreSQL.
    """

    def __init__(
        self,
        db: DatabaseConnection
    ):

        self.db = db

    def upsert_candle(
        self,
        candle
    ) -> int:

        connection = self.db.connect()

        query = """
            INSERT INTO candles (
                instrument_id,
                timestamp,
                timeframe,
                open_price,
                high_price,
                low_price,
                close_price,
                volume
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            ON CONFLICT (
                instrument_id,
                timestamp,
                timeframe
            )
            DO UPDATE SET
                open_price = EXCLUDED.open_price,
                high_price = EXCLUDED.high_price,
                low_price = EXCLUDED.low_price,
                close_price = EXCLUDED.close_price,
                volume = EXCLUDED.volume
            RETURNING candle_id
        """

        values = (
            candle.instrument_id,
            candle.timestamp,
            candle.timeframe,
            candle.open_price,
            candle.high_price,
            candle.low_price,
            candle.close_price,
            candle.volume
        )

        cursor = connection.cursor()

        try:

            cursor.execute(
                query,
                values
            )

            candle_id = cursor.fetchone()[0]

            connection.commit()

            return candle_id

        except Exception:

            connection.rollback()

            raise

        finally:

            cursor.close()

    def insert_candle_if_missing(
        self,
        candle
    ) -> int | None:

        query = """
            INSERT INTO candles (
                instrument_id,
                timestamp,
                timeframe,
                open_price,
                high_price,
                low_price,
                close_price,
                volume
            )
            VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s
            )
            ON CONFLICT (
                instrument_id,
                timestamp,
                timeframe
            )
            DO NOTHING
            RETURNING candle_id
        """

        connection = self.db.connect()
        cursor = connection.cursor()

        try:

            cursor.execute(
                query,
                (
                    candle.instrument_id,
                    candle.timestamp,
                    candle.timeframe,
                    candle.open_price,
                    candle.high_price,
                    candle.low_price,
                    candle.close_price,
                    candle.volume
                )
            )

            row = cursor.fetchone()

            connection.commit()

            if row is None:
                return None

            return row[0]

        finally:

            cursor.close()

    def insert_candles_if_missing(
        self,
        candles: list
    ) -> tuple[int, int]:
        """
        Insert candles that do not already exist.

        Returns:
            (inserted_count, skipped_count)
        """

        inserted = 0
        skipped = 0

        for candle in candles:

            candle_id = self.insert_candle_if_missing(
                candle
            )

            if candle_id is None:
                skipped += 1
            else:
                inserted += 1

        return inserted, skipped

    def candle_exists(
        self,
        instrument_id: int,
        timestamp,
        timeframe: str
    ) -> bool:

        connection = self.db.connect()

        query = """
            SELECT 1
            FROM candles
            WHERE instrument_id = %s
              AND timestamp = %s
              AND timeframe = %s
            LIMIT 1
        """

        cursor = connection.cursor()

        try:

            cursor.execute(
                query,
                (
                    instrument_id,
                    timestamp,
                    timeframe
                )
            )

            return cursor.fetchone() is not None

        finally:

            cursor.close()

    def get_candles_between(
        self,
        instrument_id: int,
        timeframe: str,
        start_timestamp,
        end_timestamp
    ) -> list:

        connection = self.db.connect()

        query = """
            SELECT
                candle_id,
                instrument_id,
                timestamp,
                timeframe,
                open_price,
                high_price,
                low_price,
                close_price,
                volume,
                created_at
            FROM candles
            WHERE instrument_id = %s
              AND timeframe = %s
              AND timestamp >= %s
              AND timestamp < %s
            ORDER BY timestamp ASC
        """

        cursor = connection.cursor()

        try:

            cursor.execute(
                query,
                (
                    instrument_id,
                    timeframe,
                    start_timestamp,
                    end_timestamp
                )
            )

            return cursor.fetchall()

        finally:

            cursor.close()

    def get_candle_timestamps_between(
        self,
        instrument_id: int,
        timeframe: str,
        start_timestamp,
        end_timestamp
    ) -> set:

        connection = self.db.connect()

        query = """
            SELECT timestamp
            FROM candles
            WHERE instrument_id = %s
              AND timeframe = %s
              AND timestamp >= %s
              AND timestamp < %s
            ORDER BY timestamp ASC
        """

        cursor = connection.cursor()

        try:

            cursor.execute(
                query,
                (
                    instrument_id,
                    timeframe,
                    start_timestamp,
                    end_timestamp
                )
            )

            return {
                row[0]
                for row in cursor.fetchall()
            }

        finally:

            cursor.close()

    def get_candles_before(
        self,
        instrument_id: int,
        timeframe: str,
        before_timestamp,
        limit: int = 100
    ) -> list:

        connection = self.db.connect()

        query = """
            SELECT
                candle_id,
                instrument_id,
                timestamp,
                timeframe,
                open_price,
                high_price,
                low_price,
                close_price,
                volume,
                created_at
            FROM candles
            WHERE instrument_id = %s
              AND timeframe = %s
              AND timestamp < %s
            ORDER BY timestamp DESC
            LIMIT %s
        """

        cursor = connection.cursor()

        try:

            cursor.execute(
                query,
                (
                    instrument_id,
                    timeframe,
                    before_timestamp,
                    limit
                )
            )

            return cursor.fetchall()

        finally:

            cursor.close()

    def get_candles(
        self,
        instrument_id: int,
        timeframe: str,
        limit: int = 100
    ) -> list:

        connection = self.db.connect()

        query = """
            SELECT
                candle_id,
                instrument_id,
                timestamp,
                timeframe,
                open_price,
                high_price,
                low_price,
                close_price,
                volume,
                created_at
            FROM candles
            WHERE instrument_id = %s
              AND timeframe = %s
            ORDER BY timestamp DESC
            LIMIT %s
        """

        cursor = connection.cursor()

        try:

            cursor.execute(
                query,
                (
                    instrument_id,
                    timeframe,
                    limit
                )
            )

            return cursor.fetchall()

        finally:

            cursor.close()

    def get_candles_chronological(
        self,
        instrument_id: int,
        timeframe: str,
        limit: int = 100
    ) -> list:

        connection = self.db.connect()

        query = """
            SELECT *
            FROM (
                SELECT
                    candle_id,
                    instrument_id,
                    timestamp,
                    timeframe,
                    open_price,
                    high_price,
                    low_price,
                    close_price,
                    volume,
                    created_at
                FROM candles
                WHERE instrument_id = %s
                  AND timeframe = %s
                ORDER BY timestamp DESC
                LIMIT %s
            ) recent
            ORDER BY timestamp ASC
        """

        cursor = connection.cursor()

        try:

            cursor.execute(
                query,
                (
                    instrument_id,
                    timeframe,
                    limit
                )
            )

            return cursor.fetchall()

        finally:

            cursor.close()


# --------------------------------------------------
# Indicator Repository
# --------------------------------------------------

class IndicatorRepository:
    """
    Handles persistence of calculated technical indicators
    into PostgreSQL.

    Stored indicators include:

        RSI 14
        EMA 9
        EMA 20
        EMA 50
        VWAP
        ATR 14
        Volume SMA 20
        MACD 12/26/9
        MACD Signal 9
        MACD Histogram
    """

    def __init__(
        self,
        db: DatabaseConnection
    ):

        self.db = db

    def upsert_indicators(
        self,
        instrument_id: int,
        timestamp,
        timeframe: str,
        values
    ) -> int:

        connection = self.db.connect()

        query = """
            INSERT INTO indicators (
                instrument_id,
                timestamp,
                timeframe,
                rsi_14,
                ema_9,
                ema_20,
                ema_50,
                vwap,
                atr_14,
                volume_sma_20,
                macd,
                macd_signal,
                macd_histogram
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            ON CONFLICT (
                instrument_id,
                timestamp,
                timeframe
            )
            DO UPDATE SET
                rsi_14 = EXCLUDED.rsi_14,
                ema_9 = EXCLUDED.ema_9,
                ema_20 = EXCLUDED.ema_20,
                ema_50 = EXCLUDED.ema_50,
                vwap = EXCLUDED.vwap,
                atr_14 = EXCLUDED.atr_14,
                volume_sma_20 = EXCLUDED.volume_sma_20,
                macd = EXCLUDED.macd,
                macd_signal = EXCLUDED.macd_signal,
                macd_histogram = EXCLUDED.macd_histogram,
                updated_at = NOW()
            RETURNING indicator_id
        """

        values_to_insert = (
            instrument_id,
            timestamp,
            timeframe,
            values.rsi_14,
            values.ema_9,
            values.ema_20,
            values.ema_50,
            values.vwap,
            values.atr_14,
            values.volume_sma_20,
            values.macd,
            values.macd_signal,
            values.macd_histogram
        )

        cursor = connection.cursor()

        try:

            cursor.execute(
                query,
                values_to_insert
            )

            indicator_id = (
                cursor.fetchone()[0]
            )

            connection.commit()

            return indicator_id

        except Exception:

            connection.rollback()

            raise

        finally:

            cursor.close()

    def get_indicator(
        self,
        instrument_id: int,
        timestamp,
        timeframe: str
    ):
        """
        Return the indicator row for one exact
        instrument/timestamp/timeframe combination.
        """

        connection = self.db.connect()

        query = """
            SELECT
                indicator_id,
                instrument_id,
                timestamp,
                timeframe,
                rsi_14,
                ema_9,
                ema_20,
                ema_50,
                vwap,
                atr_14,
                volume_sma_20,
                macd,
                macd_signal,
                macd_histogram,
                created_at,
                updated_at
            FROM indicators
            WHERE instrument_id = %s
              AND timestamp = %s
              AND timeframe = %s
        """

        cursor = connection.cursor()

        try:

            cursor.execute(
                query,
                (
                    instrument_id,
                    timestamp,
                    timeframe
                )
            )

            return cursor.fetchone()

        finally:

            cursor.close()

    def get_indicators(
        self,
        instrument_id: int,
        timeframe: str,
        limit: int = 100
    ) -> list:

        connection = self.db.connect()

        query = """
            SELECT
                indicator_id,
                instrument_id,
                timestamp,
                timeframe,
                rsi_14,
                ema_9,
                ema_20,
                ema_50,
                vwap,
                atr_14,
                volume_sma_20,
                macd,
                macd_signal,
                macd_histogram,
                created_at,
                updated_at
            FROM indicators
            WHERE instrument_id = %s
              AND timeframe = %s
            ORDER BY timestamp DESC
            LIMIT %s
        """

        cursor = connection.cursor()

        try:

            cursor.execute(
                query,
                (
                    instrument_id,
                    timeframe,
                    limit
                )
            )

            return cursor.fetchall()

        finally:

            cursor.close()


# --------------------------------------------------
# Instrument Repository
# --------------------------------------------------

class InstrumentRepository:
    """
    Handles persistence of instruments into PostgreSQL.
    """

    def __init__(self, db: DatabaseConnection):

        self.db = db

    def upsert_instrument(
        self,
        symbol: str,
        exchange: str,
        isin: str,
        provider: str,
        provider_instrument_id: str,
        provider_symbol: str
    ) -> int:

        connection = self.db.connect()

        query = """
            INSERT INTO instruments (
                symbol,
                exchange,
                isin,
                provider,
                provider_instrument_id,
                provider_symbol,
                active,
                updated_at
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                TRUE,
                NOW()
            )
            ON CONFLICT (symbol, exchange)
            DO UPDATE SET
                isin = EXCLUDED.isin,
                provider = EXCLUDED.provider,
                provider_instrument_id =
                    EXCLUDED.provider_instrument_id,
                provider_symbol =
                    EXCLUDED.provider_symbol,
                active = TRUE,
                updated_at = NOW()
            RETURNING instrument_id
        """

        values = (
            symbol,
            exchange,
            isin,
            provider,
            provider_instrument_id,
            provider_symbol
        )

        cursor = connection.cursor()

        try:

            cursor.execute(
                query,
                values
            )

            instrument_id = cursor.fetchone()[0]

            connection.commit()

            return instrument_id

        except Exception:

            connection.rollback()

            raise

        finally:

            cursor.close()

    def get_instrument_by_symbol(
        self,
        symbol: str,
        exchange: str = "NSE"
    ):

        connection = self.db.connect()

        query = """
            SELECT
                instrument_id,
                symbol,
                exchange,
                isin,
                provider,
                provider_instrument_id,
                provider_symbol
            FROM instruments
            WHERE symbol = %s
              AND exchange = %s
        """

        cursor = connection.cursor()

        try:

            cursor.execute(
                query,
                (symbol, exchange)
            )

            return cursor.fetchone()

        finally:

            cursor.close()

    def get_instrument_by_provider_id(
        self,
        provider_instrument_id: str
    ) -> int | None:
        """
        Resolve an internal instrument_id using the
        provider's instrument identifier.

        Example:

            NSE_EQ|INE002A01018
                    ↓
                instrument_id
                    ↓
                    2
        """

        connection = self.db.connect()

        query = """
            SELECT
                instrument_id
            FROM instruments
            WHERE provider_instrument_id = %s
              AND active = TRUE
            LIMIT 1
        """

        cursor = connection.cursor()

        try:

            cursor.execute(
                query,
                (provider_instrument_id,)
            )

            result = cursor.fetchone()

            if result is None:

                return None

            return result[0]

        finally:

            cursor.close()

    def get_instrument_id(
        self,
        provider: str,
        provider_instrument_id: str
    ) -> int | None:
        """
        Resolve an internal instrument_id using both the provider
        and the provider's instrument identifier.

        Example:

            provider="upstox"
            provider_instrument_id="NSE_EQ|INE002A01018"
                    ↓
                instrument_id
                    ↓
                    2
        """

        connection = self.db.connect()

        query = """
            SELECT
                instrument_id
            FROM instruments
            WHERE provider = %s
              AND provider_instrument_id = %s
              AND active = TRUE
            LIMIT 1
        """

        cursor = connection.cursor()

        try:

            cursor.execute(
                query,
                (
                    provider,
                    provider_instrument_id
                )
            )

            result = cursor.fetchone()

            if result is None:

                return None

            return result[0]

        finally:

            cursor.close()

    def get_active_provider_instrument_ids(
        self
    ) -> List[str]:
        """
        Return provider instrument IDs for all active instruments.

        These IDs are used to subscribe to the Upstox
        market-data WebSocket.
        """

        connection = self.db.connect()

        query = """
            SELECT
                provider_instrument_id
            FROM instruments
            WHERE active = TRUE
              AND provider_instrument_id IS NOT NULL
            ORDER BY instrument_id
        """

        cursor = connection.cursor()

        try:

            cursor.execute(query)

            rows = cursor.fetchall()

            return [
                row[0]
                for row in rows
            ]

        finally:

            cursor.close()

    # --------------------------------------------------
    # Internal instrument IDs
    # --------------------------------------------------

    def get_active_instrument_ids(
        self
    ) -> List[int]:
        """
        Return internal instrument IDs for all active instruments.
        """

        connection = self.db.connect()

        query = """
            SELECT
                instrument_id
            FROM instruments
            WHERE active = TRUE
            ORDER BY instrument_id
        """

        cursor = connection.cursor()

        try:

            cursor.execute(query)

            rows = cursor.fetchall()

            return [
                row[0]
                for row in rows
            ]

        finally:

            cursor.close()

    def get_active_instruments_with_provider_ids(
        self
    ) -> List[tuple[int, str]]:
        """
        Return internal instrument IDs together with
        their provider instrument IDs for all active instruments.
        """

        connection = self.db.connect()

        query = """
            SELECT
                instrument_id,
                provider_instrument_id
            FROM instruments
            WHERE active = TRUE
              AND provider_instrument_id IS NOT NULL
            ORDER BY instrument_id
        """

        cursor = connection.cursor()

        try:

            cursor.execute(query)

            rows = cursor.fetchall()

            return [
                (
                    row[0],
                    row[1]
                )
                for row in rows
            ]

        finally:

            cursor.close()