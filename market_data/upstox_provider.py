import logging
from datetime import datetime, timezone
from typing import Dict, List

import upstox_client

from config.settings import Settings
from database.repository import InstrumentRepository
from market_data.base_provider import MarketDataProvider
from market_data.models import MarketTick


class UpstoxProvider(MarketDataProvider):
    """
    Upstox V3 WebSocket market-data provider.

    Responsibilities:
        1. Authenticate using the Upstox access token.
        2. Connect to Upstox MarketDataStreamerV3.
        3. Subscribe to instrument keys.
        4. Convert Upstox messages into MarketTick objects.
        5. Emit MarketTick objects through the provider callback.
        6. Track WebSocket connection state.

    This class does NOT interact directly with PostgreSQL.
    """

    def __init__(
        self,
        instrument_keys: List[str] | None = None,
        mode: str = "full",
        instrument_repository: InstrumentRepository | None = None
    ):
        super().__init__()

        self.instrument_keys = instrument_keys or []

        self.mode = mode

        self.instrument_repository = (
            instrument_repository
        )

        self.streamer = None

        self.logger = logging.getLogger(
            self.__class__.__name__
        )

        # --------------------------------------------------
        # Connection state
        # --------------------------------------------------

        self._connected = False

        self._disconnect_requested = False

    # --------------------------------------------------
    # Connection
    # --------------------------------------------------

    def connect(self) -> None:

        access_token = (
            Settings.UPSTOX_ACCESS_TOKEN
        )

        if not access_token:

            raise ValueError(
                "UPSTOX_ACCESS_TOKEN is not configured."
            )

        if self._connected:

            self.logger.warning(
                "Upstox WebSocket is already connected."
            )

            return

        self._disconnect_requested = False

        self.logger.info(
            "Creating Upstox API configuration..."
        )

        configuration = (
            upstox_client.Configuration()
        )

        configuration.access_token = (
            access_token
        )

        api_client = (
            upstox_client.ApiClient(
                configuration
            )
        )

        self.streamer = (
            upstox_client.MarketDataStreamerV3(
                api_client,
                self.instrument_keys,
                self.mode
            )
        )

        # --------------------------------------------------
        # Configure persistent auto-reconnect
        # --------------------------------------------------

        self.streamer.auto_reconnect(
            True,
            5,
            60
        )

        # --------------------------------------------------
        # Register WebSocket events
        # --------------------------------------------------

        self.streamer.on(
            "open",
            self._on_open
        )

        self.streamer.on(
            "message",
            self._on_message
        )

        self.streamer.on(
            "error",
            self._on_error
        )

        self.streamer.on(
            "close",
            self._on_close
        )

        self.streamer.on(
            "reconnecting",
            self._on_reconnecting
        )

        self.streamer.on(
            "autoReconnectStopped",
            self._on_auto_reconnect_stopped
        )

        self.logger.info(
            "Connecting to Upstox MarketDataStreamerV3..."
        )

        try:

            self.streamer.connect()

        except Exception:

            self._connected = False

            self.logger.exception(
                "Failed to connect to Upstox."
            )

            raise

    # --------------------------------------------------
    # Subscription
    # --------------------------------------------------

    def subscribe(
        self,
        instruments: List[str]
    ) -> None:

        if not self.streamer:

            raise RuntimeError(
                "Upstox streamer is not initialized."
            )

        if not instruments:

            self.logger.warning(
                "No instruments supplied for subscription."
            )

            return

        self.logger.info(
            f"Subscribing to {len(instruments)} "
            f"instruments in {self.mode} mode."
        )

        self.streamer.subscribe(
            instruments,
            self.mode
        )

        self.instrument_keys = list(
            instruments
        )

        self.logger.info(
            "Subscription request sent successfully."
        )

    # --------------------------------------------------
    # Disconnect
    # --------------------------------------------------

    def disconnect(self) -> None:

        if not self.streamer:

            self.logger.info(
                "Upstox streamer is not active."
            )

            self._connected = False

            return

        self.logger.info(
            "Disconnecting from Upstox..."
        )

        # --------------------------------------------------
        # Mark intentional shutdown BEFORE disconnect
        # --------------------------------------------------

        self._disconnect_requested = True

        try:

            self.streamer.disconnect()

        except Exception:

            self.logger.exception(
                "Error while disconnecting from Upstox."
            )

        finally:

            self._connected = False
            self.streamer = None

    # --------------------------------------------------
    # Connection status
    # --------------------------------------------------

    @property
    def is_connected(self) -> bool:

        return self._connected

    # --------------------------------------------------
    # WebSocket Events
    # --------------------------------------------------

    def _on_open(self) -> None:

        self._connected = True

        self.logger.info(
            "Connected to Upstox Market Data WebSocket."
        )

        if not self.instrument_keys:

            self.logger.warning(
                "No instruments available for subscription."
            )

            return

        self.logger.info(
            f"Subscribing to "
            f"{len(self.instrument_keys)} instruments..."
        )

        try:

            self.streamer.subscribe(
                self.instrument_keys,
                self.mode
            )

            self.logger.info(
                "Subscription request sent successfully."
            )

        except Exception:

            self.logger.exception(
                "Failed to subscribe to Upstox instruments."
            )

    def _on_message(
        self,
        message: Dict
    ) -> None:

        try:

            self.logger.debug(
                f"Upstox message received. "
                f"Type: {message.get('type')}"
            )

            message_type = message.get(
                "type"
            )

            # --------------------------------------------------
            # Market information message
            # --------------------------------------------------

            if message_type == "market_info":

                self.logger.info(
                    "Received Upstox market-info message."
                )

                return

            # --------------------------------------------------
            # Extract feeds
            # --------------------------------------------------

            feeds = message.get(
                "feeds",
                {}
            )

            # --------------------------------------------------
            # Ignore unrelated messages
            # --------------------------------------------------

            if (
                message_type not in (
                    None,
                    "live_feed"
                )
                and not feeds
            ):

                self.logger.debug(
                    f"Ignoring message type: "
                    f"{message_type}"
                )

                return

            # --------------------------------------------------
            # No market data
            # --------------------------------------------------

            if not feeds:

                self.logger.debug(
                    "Market-data message contained no feeds."
                )

                return

            self.logger.debug(
                f"Processing "
                f"{len(feeds)} instrument feed(s)."
            )

            # --------------------------------------------------
            # Process each instrument
            # --------------------------------------------------

            for (
                provider_instrument_id,
                feed
            ) in feeds.items():

                tick = self._parse_feed(
                    provider_instrument_id,
                    feed
                )

                if tick is not None:

                    self._emit_tick(
                        tick
                    )

        except Exception:

            self.logger.exception(
                "Error processing Upstox market message."
            )

    # --------------------------------------------------
    # Message Parsing
    # --------------------------------------------------

    def _parse_feed(
        self,
        provider_instrument_id: str,
        feed: Dict
    ) -> MarketTick | None:
        """
        Convert an Upstox full-feed message into
        our internal MarketTick model.

        The market event timestamp is taken from
        Upstox LTPC LTT (last traded time).

        Receipt timestamps such as currentTs are deliberately
        not used as the market tick timestamp because they
        represent feed/message timing rather than the trade
        event time used by the candle pipeline.
        """

        market_feed = (
            self._extract_market_feed(
                feed
            )
        )

        if not market_feed:

            return None

        ltpc = market_feed.get(
            "ltpc",
            {}
        )

        if not ltpc:

            return None

        ltp = ltpc.get(
            "ltp"
        )

        if ltp is None:

            return None

        timestamp = (
            self._parse_timestamp(
                ltpc.get("ltt")
            )
        )

        last_quantity = (
            self._to_int(
                ltpc.get("ltq")
            )
        )

        close_price = (
            self._to_float(
                ltpc.get("cp")
            )
        )

        bid_price, ask_price = (
            self._extract_best_bid_ask(
                market_feed
            )
        )

        volume = (
            self._extract_volume(
                market_feed
            )
        )

        instrument_id = (
            self._resolve_instrument_id(
                provider_instrument_id
            )
        )

        if instrument_id is None:

            self.logger.warning(
                "No internal instrument mapping found "
                f"for {provider_instrument_id}"
            )

            return None

        return MarketTick(
            instrument_id=instrument_id,
            timestamp=timestamp,
            last_price=self._to_float(
                ltp
            ),
            last_quantity=last_quantity,
            volume=volume,
            bid_price=bid_price,
            ask_price=ask_price,
            open_price=None,
            high_price=None,
            low_price=None,
            previous_close=close_price
        )

    # --------------------------------------------------
    # Feed Extraction
    # --------------------------------------------------

    @staticmethod
    def _extract_market_feed(
        feed: Dict
    ) -> Dict | None:

        # --------------------------------------------------
        # Current Upstox V3 full-feed format
        # --------------------------------------------------

        full_feed = feed.get(
            "fullFeed"
        )

        if full_feed:

            market_feed = (
                full_feed.get(
                    "marketFF"
                )
            )

            if market_feed:

                return market_feed

        # --------------------------------------------------
        # Older / alternate full-feed format
        # --------------------------------------------------

        full_feed = feed.get(
            "ff"
        )

        if full_feed:

            market_feed = (
                full_feed.get(
                    "marketFF"
                )
            )

            if market_feed:

                return market_feed

        # --------------------------------------------------
        # LTPC mode
        # --------------------------------------------------

        ltpc_feed = feed.get(
            "ltpc"
        )

        if ltpc_feed:

            return {
                "ltpc": ltpc_feed
            }

        return None

    # --------------------------------------------------
    # Bid / Ask
    # --------------------------------------------------

    @staticmethod
    def _extract_best_bid_ask(
        market_feed: Dict
    ) -> tuple:

        market_level = market_feed.get(
            "marketLevel",
            {}
        )

        quotes = market_level.get(
            "bidAskQuote",
            []
        )

        if not quotes:

            return None, None

        bid_price = None
        ask_price = None

        for quote in quotes:

            if not quote:

                continue

            if bid_price is None:

                bid_price = (
                    UpstoxProvider._to_float(
                        quote.get("bidP")
                    )
                )

            if ask_price is None:

                ask_price = (
                    UpstoxProvider._to_float(
                        quote.get("askP")
                    )
                )

            if (
                bid_price is not None
                and ask_price is not None
            ):

                break

        return bid_price, ask_price

    # --------------------------------------------------
    # Volume
    # --------------------------------------------------

    @staticmethod
    def _extract_volume(
        market_feed: Dict
    ) -> int | None:

        volume = market_feed.get(
            "vtt"
        )

        return UpstoxProvider._to_int(
            volume
        )

    # --------------------------------------------------
    # OHLC
    # --------------------------------------------------

    @staticmethod
    def _extract_ohlc(
        market_feed: Dict
    ) -> dict:

        market_ohlc = market_feed.get(
            "marketOHLC",
            {}
        )

        ohlc_list = market_ohlc.get(
            "ohlc",
            []
        )

        result = {}

        for candle in ohlc_list:

            interval = candle.get(
                "interval"
            )

            if not interval:

                continue

            result[interval] = {
                "open": UpstoxProvider._to_float(
                    candle.get("open")
                ),
                "high": UpstoxProvider._to_float(
                    candle.get("high")
                ),
                "low": UpstoxProvider._to_float(
                    candle.get("low")
                ),
                "close": UpstoxProvider._to_float(
                    candle.get("close")
                ),
                "volume": UpstoxProvider._to_int(
                    candle.get("vol")
                ),
                "timestamp": candle.get(
                    "ts"
                )
            }

        return result

    # --------------------------------------------------
    # Instrument Mapping
    # --------------------------------------------------

    def _resolve_instrument_id(
        self,
        provider_instrument_id: str
    ) -> int | None:

        if self.instrument_repository is None:

            self.logger.error(
                "InstrumentRepository is not configured."
            )

            return None

        return (
            self.instrument_repository
            .get_instrument_by_provider_id(
                provider_instrument_id
            )
        )

    # --------------------------------------------------
    # Utilities
    # --------------------------------------------------

    @staticmethod
    def _to_float(
        value
    ) -> float | None:

        if value is None:

            return None

        try:

            return float(value)

        except (
            TypeError,
            ValueError
        ):

            return None

    @staticmethod
    def _to_int(
        value
    ) -> int | None:

        if value is None:

            return None

        try:

            return int(value)

        except (
            TypeError,
            ValueError
        ):

            return None

    @staticmethod
    def _parse_timestamp(
        timestamp
    ) -> datetime:

        if timestamp is None:

            return datetime.now(
                timezone.utc
            )

        try:

            timestamp_ms = int(
                timestamp
            )

            return datetime.fromtimestamp(
                timestamp_ms / 1000,
                tz=timezone.utc
            )

        except (
            TypeError,
            ValueError
        ):

            return datetime.now(
                timezone.utc
            )

    # --------------------------------------------------
    # Connection Events
    # --------------------------------------------------

    def _on_error(
        self,
        error
    ) -> None:

        self.logger.error(
            f"Upstox WebSocket error: {error}"
        )

    def _on_close(
        self,
        *args
    ) -> None:

        self._connected = False

        if self._disconnect_requested:

            self.logger.info(
                "Upstox WebSocket closed intentionally."
            )

        else:

            self.logger.warning(
                "Upstox WebSocket connection closed "
                f"unexpectedly. Details: {args}"
            )

    def _on_reconnecting(
        self,
        message
    ) -> None:

        self._connected = False

        self.logger.warning(
            f"Upstox WebSocket reconnecting: "
            f"{message}"
        )

    def _on_auto_reconnect_stopped(
        self,
        message
    ) -> None:

        self._connected = False

        if self._disconnect_requested:

            self.logger.info(
                "Upstox auto-reconnect stopped "
                "because shutdown was requested."
            )

        else:

            self.logger.error(
                "Upstox auto-reconnect stopped "
                f"unexpectedly: {message}"
            )

            self._emit_failure(
                f"Upstox auto-reconnect stopped unexpectedly: {message}"
            )