# ExaFinvest Market Database - Architecture Report

**Generated:** 2026-08-31  
**Project Root:** `d:\ExaFinvest\market_database`

---

## 1. Project Overview

**Purpose:** Real-time financial market data ingestion, aggregation, and analysis pipeline.

**Key Capabilities:**
- Stream market ticks from multiple providers (Upstox, Kite)
- Aggregate ticks into OHLCV candles at various timeframes
- Calculate technical indicators (RSI, etc.)
- Persist data to PostgreSQL
- Match and manage financial instruments

**Technology Stack:**
- **Language:** Python 3.x
- **Database:** PostgreSQL (psycopg2)
- **Data Sources:** Upstox WebSocket API, Kite API
- **Key Libraries:** beautifulsoup4 (web scraping)

---

## 2. Architecture Layers

### 2.1 Presentation/CLI Layer
- `main.py` - Entry point (currently empty)
- Test files - Comprehensive test suite

### 2.2 Service Layer (Orchestration)

MarketDataService
├── Coordinates data ingestion flow
├── Manages tick buffering
├── Handles persistence batching
└── Orchestrates provider connections


### 2.3 Domain Logic Layer
- **Providers:** Multiple market data sources
- **Candle Aggregation:** Tick-to-OHLCV conversion
- **Indicators:** Technical analysis calculations
- **Matching:** Instrument name/symbol matching

### 2.4 Data Access Layer
- **Repositories:** Abstract database operations
- **Database Connection:** PostgreSQL connection management
- **Schema:** SQL table definitions

### 2.5 Configuration Layer
- `config/settings.py` - Environment-based configuration
- `config/instrument_aliases.json` - Instrument mappings

---

## 3. Core Components

### 3.1 Market Data Flow


┌─────────────────────────────────────────────────────────────────┐
│ Market Data Ingestion │
└─────────────────────────────────────────────────────────────────┘
↓
┌─────────────────────┐
│ MarketDataService │
│ (Main Orchestrator)│
└─────────────────────┘
↓
┌─────────────────────┐
│ Market Data Provider│
│ (Upstox/Kite) │
└─────────────────────┘
↓
┌─────────────────────┐
│ MarketTick │
│ (Normalized Data) │
└─────────────────────┘
↓ ↓
┌──────────────────┐ ┌──────────────────┐
│ Tick Repository │ │ CandleAggregator │
│ (Persist Ticks) │ │ (1m, 5m, etc.) │
└──────────────────┘ └──────────────────┘
↓ ↓
PostgreSQL ticks Candle Objects
↓
┌──────────────────┐
│ CandleRepository │
│(Persist Candles) │
└──────────────────┘
↓
PostgreSQL candles
↓
┌──────────────────┐
│IndicatorService │
│(Calculate RSI,etc)
└──────────────────┘
↓
PostgreSQL indicators


### 3.2 Component Breakdown

#### **MarketDataService** (`market_data/market_data_service.py`)
- **Role:** Central orchestrator of market data ingestion
- **Responsibilities:**
  - Manage provider connections
  - Maintain tick buffer (batch size: 250 ticks)
  - Coordinate persistence to PostgreSQL
  - Manage candle aggregation
  - Trigger indicator calculations
- **Key Operations:**
  - `start()` - Initialize ingestion pipeline
  - `subscribe_to_instruments()` - Register instrument subscriptions
  - `on_tick()` - Callback for new market ticks
  - Statistics tracking (total_ticks_received, total_ticks_persisted)

#### **MarketDataProvider** (`market_data/base_provider.py`)
- **Pattern:** Abstract Base Class (ABC)
- **Implementations:**
  - `UpstoxProvider` - Upstox WebSocket streaming
  - `KiteProvider` - Kite WebSocket streaming
- **Interface:**
  - `connect()` - Establish connection
  - `subscribe(instruments: List[str])` - Subscribe to instruments
  - `disconnect()` - Close connection
  - `set_tick_callback()` - Register tick handler
  - `_emit_tick()` - Send normalized tick

#### **MarketTick** (`market_data/models.py`)
- **Purpose:** Provider-agnostic tick representation
- **Fields:**
  - `instrument_id`, `timestamp` (required)
  - OHLC data: `open_price`, `high_price`, `low_price`, `close_price` (optional)
  - Bid/Ask: `bid_price`, `ask_price` (optional)
  - Volume: `volume`, `last_quantity` (optional)
  - `previous_close` (optional)

#### **CandleAggregator** (`market_data/candle_aggregator.py`)
- **Purpose:** Convert market ticks to OHLCV candles
- **Key Logic:**
  - Volume delta calculation (provider volume is cumulative)
  - Timeframe bucketing (1m, 5m, 15m, etc.)
  - State management: `_candles`, `_last_volume`
- **Operations:**
  - `process_tick(tick, timeframe)` → Returns completed Candle or None
  - `_get_bucket_timestamp()` - Align tick to candle timeframe
  - `_calculate_volume_delta()` - Convert cumulative to delta volume

#### **Candle** (`market_data/candle.py`)
- **Represents:** OHLCV data for a specific timeframe
- **Fields:** instrument_id, timestamp, timeframe, open, high, low, close, volume

---

## 4. Database Layer

### 4.1 DatabaseConnection (`database/connection.py`)
- **Pattern:** Singleton-like connection manager
- **Driver:** psycopg2
- **Configuration:** From `Settings` (environment variables)
- **Methods:**
  - `connect()` - Get or create connection
  - `close()` - Terminate connection

### 4.2 Repositories (`database/repository.py`)

| Repository | Responsibility |
|---|---|
| `TickRepository` | Persist market ticks in batch |
| `CandleRepository` | Persist OHLCV candles |
| `InstrumentRepository` | Query active instruments, provider IDs |
| `IndicatorRepository` | Persist calculated indicators |

**Key Pattern:** Batch insert operations for performance

### 4.3 Database Schema (`database/schema.sql`)
- Tables: instruments, ticks, candles, indicators
- Indexes optimized for time-series queries

---

## 5. Configuration

### 5.1 Settings (`config/settings.py`)
- **Provider:** Upstox API credentials
- **Database:** PostgreSQL connection details (host, port, database, user, password)

**Loading:** Environment variables via `python-dotenv`

### 5.2 Instrument Aliases (`config/instrument_aliases.json`)
- Maps trading symbol variations to canonical names

---

## 6. Indicator System

### 6.1 IndicatorService (`market_data/indicator_service.py`)
- **Purpose:** Calculate technical indicators on candles
- **Supported Indicators:**
  - RSI (Relative Strength Index)

---

## 7. Instrument Management

### 7.1 InstrumentMaster (`market_data/instrument_master.py`)
- **Purpose:** Manage instrument definitions from provider
- **Class:** `UpstoxInstrumentMaster`
- **Operations:**
  - Download official Upstox NSE instrument JSON (gzip)
  - Parse and filter NSE equity instruments
  - Extract instrument metadata

### 7.2 InstrumentMatcher (`market_data/instrument_matcher.py`)
- **Purpose:** Match user-provided symbols to provider instruments
- **Strategy:** Fuzzy matching, alias lookup

### 7.3 InstrumentSync (`market_data/instrument_sync.py`)
- **Purpose:** Keep local instrument database synchronized with provider
- **Process:** Download, match, and store instruments

---

## 8. Data Flow Sequence

### 8.1 Initialization

MarketDataService.start()
├─ Load active instruments from PostgreSQL
├─ Initialize UpstoxProvider
├─ Set tick callback
└─ Subscribe to instruments


### 8.2 Tick Processing (per provider tick)

Provider.on_tick(raw_data)
├─ Normalize to MarketTick
├─ Emit via callback
└─ MarketDataService.on_tick(MarketTick)
├─ Add to tick buffer
├─ CandleAggregator.process_tick()
│ └─ Emit completed candle if timeframe boundary crossed
├─ If buffer full:
│ ├─ TickRepository.save_ticks()
│ ├─ CandleRepository.save_candles()
│ └─ IndicatorService.calculate()
└─ Update statistics


---

## 9. Testing Infrastructure

Comprehensive test coverage:

| Test Module | Scope |
|---|---|
| `test_candle_aggregator.py` | Tick→Candle conversion logic |
| `test_candle_service.py` | Candle service operations |
| `test_database.py` | Database connection & operations |
| `test_indicator_*.py` | Indicator calculations |
| `test_instrument_*.py` | Instrument matching & loading |
| `test_market_*.py` | Market data flow |
| `test_upstox.py` | Upstox provider integration |
| `test_provider.py` | Base provider logic |

---

## 10. Key Design Patterns

### 10.1 Abstract Factory Pattern
- `MarketDataProvider` base class
- Implementations: UpstoxProvider, KiteProvider

### 10.2 Repository Pattern
- Data access abstraction
- Batch operations for performance
- Multiple repository types for different entities

### 10.3 Publish-Subscribe Pattern
- Provider emits ticks via callback
- Service subscribes to provider events

### 10.4 State Management
- CandleAggregator maintains state per instrument/timeframe
- Tick buffer in MarketDataService

### 10.5 Configuration Management
- Environment-based settings
- Centralized in `config.settings`

---

## 11. Module Dependencies

### 11.1 Import Graph (Top-Level)

main.py
├── market_data.market_data_service
├── database.connection
└── config.settings

MarketDataService
├── database.connection
├── database.repository
├── market_data.upstox_provider
├── market_data.candle_aggregator
├── market_data.indicator_service
└── market_data.models

UpstoxProvider
├── market_data.base_provider (extends)
├── market_data.models
└── config.settings

CandleAggregator
├── market_data.candle
└── market_data.models


### 11.2 External Dependencies
- **psycopg2** - PostgreSQL driver
- **beautifulsoup4** - HTML/XML parsing
- **python-dotenv** - Environment configuration
- **requests** - HTTP client (instrument downloads)

---

## 12. Data Persistence Strategy

### 12.1 Buffering
- **Tick Buffer:** Accumulates up to 250 ticks before persistence
- **Benefits:** Reduced database round-trips, improved throughput

### 12.2 Batch Insert
- SQL batch operations via `cursor.executemany()`
- Significant performance improvement over individual inserts

### 12.3 Time-Series Optimization
- PostgreSQL schema likely includes indexes on:
  - `(instrument_id, timestamp)`
  - `timestamp` (for range queries)

---

## 13. Configuration & Environment

### 13.1 Required Environment Variables

UPSTOX_ACCESS_TOKEN=<token>
DB_HOST=localhost
DB_PORT=5432
DB_NAME=exafinvest_market
DB_USER=postgres
DB_PASSWORD=<password>


### 13.2 File Paths
- Data: `data/`
- Logs: `logs/` (application logs)
- Config: `config/` (settings, aliases)

---

## 14. System Constraints & Considerations

### 14.1 Performance
- **Tick Buffer Size:** 250 ticks (tunable in MarketDataService)
- **Provider:** Limited by WebSocket subscription capacity
- **Database:** Index optimization critical for real-time queries

### 14.2 Scalability
- **Current Design:** Single process, multi-threaded
- **Bottleneck:** Database writes (partially mitigated by batching)
- **Future:** Consider message queue (RabbitMQ, Kafka) for scale-out

### 14.3 Reliability
- **Connection Management:** Providers must handle reconnection
- **Error Handling:** Repositories should handle transaction failures
- **Data Consistency:** Tick → Candle → Indicator flow must be atomic per batch

### 14.4 Supported Timeframes
- Implied: 1m (default), likely 5m, 15m, etc.
- Configurable in CandleAggregator.process_tick()

---

## 15. Future Extensibility

### 15.1 Adding New Providers
1. Extend `MarketDataProvider` base class
2. Implement `connect()`, `subscribe()`, `disconnect()`
3. Normalize data to `MarketTick`
4. Register in `MarketDataService`

### 15.2 Adding New Indicators
1. Create calculator in `market_data/`
2. Extend `IndicatorService`
3. Add repository persistence

### 15.3 Adding New Timeframes
- Transparently supported by `CandleAggregator`
- Pass timeframe string to `process_tick()`

---

## 16. Summary

The **ExaFinvest Market Database** is a well-architected, scalable real-time market data pipeline with:

✅ **Clean Separation of Concerns**
- Provider abstraction → normalized tick model → aggregation → persistence

✅ **Performance Optimization**
- Batched database operations, tick buffering

✅ **Extensibility**
- Abstract provider pattern, pluggable indicators

✅ **Comprehensive Testing**
- Unit tests for all major components

✅ **Configuration Management**
- Environment-based, centralized settings

The system is production-ready for single-provider deployments and can scale with message queues for multi-provider scenarios.