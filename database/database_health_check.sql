-- ============================================================
-- ExaFinvest Database Health Check
-- ============================================================


-- ============================================================
-- 1. TABLE ROW COUNTS
-- ============================================================

SELECT
    'instruments' AS table_name,
    COUNT(*) AS row_count
FROM instruments

UNION ALL

SELECT
    'ticks',
    COUNT(*)
FROM ticks

UNION ALL

SELECT
    'candles',
    COUNT(*)
FROM candles

UNION ALL

SELECT
    'indicators',
    COUNT(*)
FROM indicators;


-- ============================================================
-- 2. ACTIVE INSTRUMENTS
-- ============================================================

SELECT
    COUNT(*) AS total_instruments,
    COUNT(*) FILTER (WHERE active = TRUE) AS active_instruments,
    COUNT(*) FILTER (WHERE active = FALSE) AS inactive_instruments
FROM instruments;


-- ============================================================
-- 3. ORPHAN TICKS
-- ============================================================

SELECT COUNT(*) AS orphan_ticks
FROM ticks t
LEFT JOIN instruments i
    ON i.instrument_id = t.instrument_id
WHERE i.instrument_id IS NULL;


-- ============================================================
-- 4. ORPHAN CANDLES
-- ============================================================

SELECT COUNT(*) AS orphan_candles
FROM candles c
LEFT JOIN instruments i
    ON i.instrument_id = c.instrument_id
WHERE i.instrument_id IS NULL;


-- ============================================================
-- 5. ORPHAN INDICATORS
-- ============================================================

SELECT COUNT(*) AS orphan_indicators
FROM indicators ind
LEFT JOIN instruments i
    ON i.instrument_id = ind.instrument_id
WHERE i.instrument_id IS NULL;


-- ============================================================
-- 6. DUPLICATE CANDLES
-- ============================================================

SELECT
    instrument_id,
    timestamp,
    timeframe,
    COUNT(*) AS duplicate_count
FROM candles
GROUP BY
    instrument_id,
    timestamp,
    timeframe
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC;


-- ============================================================
-- 7. DUPLICATE INDICATORS
-- ============================================================

SELECT
    instrument_id,
    timestamp,
    timeframe,
    COUNT(*) AS duplicate_count
FROM indicators
GROUP BY
    instrument_id,
    timestamp,
    timeframe
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC;


-- ============================================================
-- 8. INVALID CANDLE OHLC
-- ============================================================

SELECT
    candle_id,
    instrument_id,
    timestamp,
    open_price,
    high_price,
    low_price,
    close_price
FROM candles
WHERE
       high_price < low_price
    OR high_price < open_price
    OR high_price < close_price
    OR low_price > open_price
    OR low_price > close_price
ORDER BY timestamp DESC;


-- ============================================================
-- 9. NEGATIVE CANDLE VOLUME
-- ============================================================

SELECT
    candle_id,
    instrument_id,
    timestamp,
    volume
FROM candles
WHERE volume < 0
ORDER BY timestamp DESC;


-- ============================================================
-- 10. INVALID TICK PRICES
-- ============================================================

SELECT
    tick_id,
    instrument_id,
    timestamp,
    last_price,
    bid_price,
    ask_price
FROM ticks
WHERE
       last_price <= 0
    OR bid_price <= 0
    OR ask_price <= 0
ORDER BY timestamp DESC;


-- ============================================================
-- 11. INVALID TICK VOLUME
-- ============================================================

SELECT
    tick_id,
    instrument_id,
    timestamp,
    volume,
    last_quantity
FROM ticks
WHERE
       volume < 0
    OR last_quantity < 0
ORDER BY timestamp DESC;


-- ============================================================
-- 12. BID / ASK SANITY
-- ============================================================

SELECT
    tick_id,
    instrument_id,
    timestamp,
    bid_price,
    ask_price
FROM ticks
WHERE
    bid_price IS NOT NULL
    AND ask_price IS NOT NULL
    AND bid_price > ask_price
ORDER BY timestamp DESC;


-- ============================================================
-- 13. CANDLE / INDICATOR ALIGNMENT
-- ============================================================

SELECT
    c.instrument_id,
    c.timestamp,
    c.timeframe
FROM candles c
LEFT JOIN indicators i
    ON  i.instrument_id = c.instrument_id
    AND i.timestamp = c.timestamp
    AND i.timeframe = c.timeframe
WHERE i.indicator_id IS NULL
ORDER BY c.timestamp DESC;


-- ============================================================
-- 14. INDICATORS WITHOUT CANDLES
-- ============================================================

SELECT
    i.indicator_id,
    i.instrument_id,
    i.timestamp,
    i.timeframe
FROM indicators i
LEFT JOIN candles c
    ON  c.instrument_id = i.instrument_id
    AND c.timestamp = i.timestamp
    AND c.timeframe = i.timeframe
WHERE c.candle_id IS NULL
ORDER BY i.timestamp DESC;


-- ============================================================
-- 15. LATEST DATA PER INSTRUMENT
-- ============================================================

SELECT
    i.instrument_id,
    i.symbol,
    i.exchange,
    i.active,

    MAX(t.timestamp) AS latest_tick,

    MAX(c.timestamp) AS latest_candle,

    MAX(ind.timestamp) AS latest_indicator

FROM instruments i

LEFT JOIN ticks t
    ON t.instrument_id = i.instrument_id

LEFT JOIN candles c
    ON c.instrument_id = i.instrument_id

LEFT JOIN indicators ind
    ON ind.instrument_id = i.instrument_id

GROUP BY
    i.instrument_id,
    i.symbol,
    i.exchange,
    i.active

ORDER BY i.instrument_id;


-- ============================================================
-- 16. DATA RANGE
-- ============================================================

SELECT
    'ticks' AS table_name,
    MIN(timestamp) AS earliest_timestamp,
    MAX(timestamp) AS latest_timestamp,
    COUNT(*) AS rows
FROM ticks

UNION ALL

SELECT
    'candles',
    MIN(timestamp),
    MAX(timestamp),
    COUNT(*)
FROM candles

UNION ALL

SELECT
    'indicators',
    MIN(timestamp),
    MAX(timestamp),
    COUNT(*)
FROM indicators;