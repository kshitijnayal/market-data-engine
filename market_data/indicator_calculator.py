from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from market_data.candle import Candle


@dataclass
class IndicatorValues:
    """
    Calculated technical indicators for one candle.
    """

    rsi_14: Optional[Decimal] = None

    ema_9: Optional[Decimal] = None
    ema_20: Optional[Decimal] = None
    ema_50: Optional[Decimal] = None

    vwap: Optional[Decimal] = None

    atr_14: Optional[Decimal] = None

    volume_sma_20: Optional[Decimal] = None

    macd: Optional[Decimal] = None
    macd_signal: Optional[Decimal] = None
    macd_histogram: Optional[Decimal] = None


class IndicatorCalculator:
    """
    Calculates technical indicators from completed candles.

    The calculator maintains independent state for every:

        (instrument_id, timeframe)

    combination.

    Supported indicators:

        EMA 9
        EMA 20
        EMA 50
        RSI 14
        ATR 14
        Volume SMA 20
        VWAP
        MACD 12/26/9
        MACD Signal 9
        MACD Histogram

    MACD is calculated from candle close prices:

        EMA 12
        EMA 26

        MACD =
            EMA 12 - EMA 26

        Signal =
            9-period EMA of MACD

        Histogram =
            MACD - Signal

    VWAP is reset automatically when the trading date changes.

    Candle prices may arrive as floats from the market-data
    layer. They are converted to Decimal before indicator
    calculations to avoid float/Decimal arithmetic errors.

    This class does not interact with:

        - PostgreSQL
        - Upstox
        - WebSockets
        - repositories
    """

    RSI_PERIOD = 14
    ATR_PERIOD = 14
    VOLUME_SMA_PERIOD = 20

    MACD_FAST_PERIOD = 12
    MACD_SLOW_PERIOD = 26
    MACD_SIGNAL_PERIOD = 9

    def __init__(self):

        # --------------------------------------------------
        # Previous close
        # --------------------------------------------------

        self._previous_close = {}

        # --------------------------------------------------
        # EMA state
        # --------------------------------------------------

        self._ema_9 = {}
        self._ema_20 = {}
        self._ema_50 = {}

        # --------------------------------------------------
        # MACD state
        #
        # MACD requires:
        #
        #     EMA 12
        #     EMA 26
        #
        # The signal line is a 9-period EMA of MACD.
        # --------------------------------------------------

        self._macd_ema_12 = {}
        self._macd_ema_26 = {}
        self._macd_signal = {}

        # --------------------------------------------------
        # RSI state
        # --------------------------------------------------

        self._rsi_gains = {}
        self._rsi_losses = {}

        # --------------------------------------------------
        # ATR state
        # --------------------------------------------------

        self._atr_values = {}

        # --------------------------------------------------
        # Volume SMA state
        # --------------------------------------------------

        self._volume_history = {}

        # --------------------------------------------------
        # VWAP state
        # --------------------------------------------------

        self._vwap_data = {}

        # --------------------------------------------------
        # VWAP trading date
        #
        # Stores the date for which the current VWAP
        # accumulation belongs.
        # --------------------------------------------------

        self._vwap_date = {}

    # ======================================================
    # DECIMAL CONVERSION
    # ======================================================

    @staticmethod
    def _to_decimal(
        value
    ) -> Decimal:
        """
        Convert a numeric value to Decimal safely.

        Using str(value) avoids importing the binary
        floating-point representation into Decimal.

        Example:

            Decimal(str(100.05))

        instead of:

            Decimal(100.05)
        """

        return Decimal(str(value))

    # ======================================================
    # MAIN CALCULATION
    # ======================================================

    def calculate(
        self,
        candle: Candle
    ) -> IndicatorValues:

        key = (
            candle.instrument_id,
            candle.timeframe
        )

        # --------------------------------------------------
        # Convert close price to Decimal
        # --------------------------------------------------

        if candle.close_price is None:

            return IndicatorValues()

        close = self._to_decimal(
            candle.close_price
        )

        # --------------------------------------------------
        # EMA
        # --------------------------------------------------

        ema_9 = self._calculate_ema(
            key=key,
            price=close,
            period=9,
            storage=self._ema_9
        )

        ema_20 = self._calculate_ema(
            key=key,
            price=close,
            period=20,
            storage=self._ema_20
        )

        ema_50 = self._calculate_ema(
            key=key,
            price=close,
            period=50,
            storage=self._ema_50
        )

        # --------------------------------------------------
        # MACD 12/26/9
        # --------------------------------------------------

        macd, macd_signal, macd_histogram = (
            self._calculate_macd(
                key,
                close
            )
        )

        # --------------------------------------------------
        # RSI
        # --------------------------------------------------

        rsi_14 = self._calculate_rsi(
            key,
            close
        )

        # --------------------------------------------------
        # ATR
        # --------------------------------------------------

        atr_14 = self._calculate_atr(
            key,
            candle
        )

        # --------------------------------------------------
        # Volume SMA
        # --------------------------------------------------

        volume_sma_20 = self._calculate_volume_sma(
            key,
            candle.volume
        )

        # --------------------------------------------------
        # VWAP
        # --------------------------------------------------

        vwap = self._calculate_vwap(
            key,
            candle
        )

        # --------------------------------------------------
        # Store previous close LAST
        #
        # RSI and ATR require the previous candle close.
        # --------------------------------------------------

        self._previous_close[key] = close

        return IndicatorValues(
            rsi_14=rsi_14,
            ema_9=ema_9,
            ema_20=ema_20,
            ema_50=ema_50,
            vwap=vwap,
            atr_14=atr_14,
            volume_sma_20=volume_sma_20,
            macd=macd,
            macd_signal=macd_signal,
            macd_histogram=macd_histogram
        )

    # ======================================================
    # EMA
    # ======================================================

    @staticmethod
    def _calculate_ema(
        key,
        price: Decimal,
        period: int,
        storage: dict
    ) -> Decimal:
        """
        Calculate EMA using recursive smoothing.

        First observation:

            EMA = price

        Subsequent observations:

            EMA =
                previous EMA
                +
                multiplier * (price - previous EMA)

        multiplier:

            2 / (period + 1)
        """

        previous_ema = storage.get(key)

        # --------------------------------------------------
        # First observation
        # --------------------------------------------------

        if previous_ema is None:

            ema = price

        else:

            multiplier = (
                Decimal("2")
                / Decimal(period + 1)
            )

            ema = (
                previous_ema
                + multiplier
                * (price - previous_ema)
            )

        storage[key] = ema

        return ema

    # ======================================================
    # MACD 12/26/9
    # ======================================================

    def _calculate_macd(
        self,
        key,
        close: Decimal
    ) -> tuple[
        Decimal,
        Decimal,
        Decimal
    ]:
        """
        Calculate standard MACD using recursive EMAs.

        Fast EMA:

            EMA 12

        Slow EMA:

            EMA 26

        MACD:

            EMA 12 - EMA 26

        Signal:

            9-period EMA of MACD

        Histogram:

            MACD - Signal

        The EMA calculation follows the same recursive
        convention used by the existing EMA indicators:

            First observation:
                EMA = current value

            Subsequent observations:
                EMA =
                    previous EMA
                    +
                    multiplier * (current - previous EMA)

        MACD therefore becomes available from the first
        candle, consistent with the calculator's existing
        EMA convention.
        """

        # --------------------------------------------------
        # EMA 12
        # --------------------------------------------------

        ema_12 = self._calculate_ema(
            key=key,
            price=close,
            period=self.MACD_FAST_PERIOD,
            storage=self._macd_ema_12
        )

        # --------------------------------------------------
        # EMA 26
        # --------------------------------------------------

        ema_26 = self._calculate_ema(
            key=key,
            price=close,
            period=self.MACD_SLOW_PERIOD,
            storage=self._macd_ema_26
        )

        # --------------------------------------------------
        # MACD line
        # --------------------------------------------------

        macd = (
            ema_12
            - ema_26
        )

        # --------------------------------------------------
        # Signal line
        #
        # Signal is a 9-period EMA of the MACD line.
        # --------------------------------------------------

        macd_signal = self._calculate_ema(
            key=key,
            price=macd,
            period=self.MACD_SIGNAL_PERIOD,
            storage=self._macd_signal
        )

        # --------------------------------------------------
        # Histogram
        # --------------------------------------------------

        macd_histogram = (
            macd
            - macd_signal
        )

        return (
            macd,
            macd_signal,
            macd_histogram
        )

    # ======================================================
    # RSI 14
    # ======================================================

    def _calculate_rsi(
        self,
        key,
        close: Decimal
    ) -> Optional[Decimal]:
        """
        Calculate RSI using a rolling 14-change window.

        RSI requires:

            14 price changes

        Therefore the first candle cannot produce RSI.

        Once 14 changes exist:

            Average Gain =
                sum(gains) / 14

            Average Loss =
                sum(losses) / 14

            RS =
                Average Gain / Average Loss

            RSI =
                100 - (100 / (1 + RS))
        """

        previous_close = (
            self._previous_close.get(key)
        )

        # --------------------------------------------------
        # First candle
        # --------------------------------------------------

        if previous_close is None:

            return None

        # --------------------------------------------------
        # Price change
        # --------------------------------------------------

        change = (
            close - previous_close
        )

        gain = max(
            change,
            Decimal("0")
        )

        loss = max(
            -change,
            Decimal("0")
        )

        # --------------------------------------------------
        # Rolling windows
        # --------------------------------------------------

        gains = (
            self._rsi_gains.setdefault(
                key,
                deque(
                    maxlen=self.RSI_PERIOD
                )
            )
        )

        losses = (
            self._rsi_losses.setdefault(
                key,
                deque(
                    maxlen=self.RSI_PERIOD
                )
            )
        )

        gains.append(gain)
        losses.append(loss)

        # --------------------------------------------------
        # RSI warm-up
        # --------------------------------------------------

        if len(gains) < self.RSI_PERIOD:

            return None

        # --------------------------------------------------
        # Average gain/loss
        # --------------------------------------------------

        average_gain = (
            sum(gains)
            / Decimal(self.RSI_PERIOD)
        )

        average_loss = (
            sum(losses)
            / Decimal(self.RSI_PERIOD)
        )

        # --------------------------------------------------
        # No losses
        # --------------------------------------------------

        if average_loss == Decimal("0"):

            # No movement at all.
            if average_gain == Decimal("0"):

                return Decimal("50")

            # Only gains.
            return Decimal("100")

        # --------------------------------------------------
        # RSI
        # --------------------------------------------------

        relative_strength = (
            average_gain
            / average_loss
        )

        rsi = (
            Decimal("100")
            - (
                Decimal("100")
                / (
                    Decimal("1")
                    + relative_strength
                )
            )
        )

        return rsi

    # ======================================================
    # ATR 14
    # ======================================================

    def _calculate_atr(
        self,
        key,
        candle: Candle
    ) -> Optional[Decimal]:
        """
        Calculate Average True Range over 14 candles.

        True Range:

            max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close)
            )

        ATR becomes available after 14 true-range
        observations.
        """

        # --------------------------------------------------
        # Required candle fields
        # --------------------------------------------------

        if (
            candle.high_price is None
            or candle.low_price is None
            or candle.close_price is None
        ):

            return None

        # --------------------------------------------------
        # Convert candle prices to Decimal
        # --------------------------------------------------

        high_price = self._to_decimal(
            candle.high_price
        )

        low_price = self._to_decimal(
            candle.low_price
        )

        close_price = self._to_decimal(
            candle.close_price
        )

        previous_close = (
            self._previous_close.get(key)
        )

        # --------------------------------------------------
        # First candle
        # --------------------------------------------------

        if previous_close is None:

            true_range = (
                high_price
                - low_price
            )

        else:

            true_range = max(
                high_price
                - low_price,

                abs(
                    high_price
                    - previous_close
                ),

                abs(
                    low_price
                    - previous_close
                )
            )

        # --------------------------------------------------
        # Rolling TR window
        # --------------------------------------------------

        atr_values = (
            self._atr_values.setdefault(
                key,
                deque(
                    maxlen=self.ATR_PERIOD
                )
            )
        )

        atr_values.append(
            true_range
        )

        # --------------------------------------------------
        # ATR warm-up
        # --------------------------------------------------

        if len(atr_values) < self.ATR_PERIOD:

            return None

        # --------------------------------------------------
        # Simple ATR
        # --------------------------------------------------

        return (
            sum(atr_values)
            / Decimal(self.ATR_PERIOD)
        )

    # ======================================================
    # VOLUME SMA 20
    # ======================================================

    def _calculate_volume_sma(
        self,
        key,
        volume: Optional[int]
    ) -> Optional[Decimal]:
        """
        Calculate 20-period simple moving average of volume.
        """

        if volume is None:

            return None

        volumes = (
            self._volume_history.setdefault(
                key,
                deque(
                    maxlen=self.VOLUME_SMA_PERIOD
                )
            )
        )

        volumes.append(
            volume
        )

        # --------------------------------------------------
        # Warm-up
        # --------------------------------------------------

        if len(volumes) < self.VOLUME_SMA_PERIOD:

            return None

        return (
            Decimal(sum(volumes))
            / Decimal(self.VOLUME_SMA_PERIOD)
        )

    # ======================================================
    # VWAP
    # ======================================================

    def _calculate_vwap(
        self,
        key,
        candle: Candle
    ) -> Optional[Decimal]:
        """
        Calculate cumulative VWAP for the current
        trading date.

        Typical Price:

            (High + Low + Close) / 3

        VWAP:

            sum(Typical Price * Volume)
            /
            sum(Volume)

        VWAP state is maintained independently for each
        instrument/timeframe.

        When the candle date changes, the previous day's
        VWAP accumulation is discarded and a new VWAP
        session begins.
        """

        # --------------------------------------------------
        # Required candle fields
        # --------------------------------------------------

        if (
            candle.high_price is None
            or candle.low_price is None
            or candle.close_price is None
        ):

            return None

        # --------------------------------------------------
        # Determine trading date
        # --------------------------------------------------

        current_date = (
            candle.timestamp.date()
        )

        previous_vwap_date = (
            self._vwap_date.get(key)
        )

        # --------------------------------------------------
        # New trading day
        #
        # VWAP is session-based, so reset only VWAP state.
        # EMA, RSI, ATR and Volume SMA are NOT reset.
        # --------------------------------------------------

        if (
            previous_vwap_date is not None
            and current_date != previous_vwap_date
        ):

            self._vwap_data.pop(
                key,
                None
            )

        # --------------------------------------------------
        # Store current VWAP trading date
        # --------------------------------------------------

        self._vwap_date[key] = current_date

        # --------------------------------------------------
        # Normalize volume to Decimal
        # --------------------------------------------------

        volume = (
            Decimal(candle.volume)
            if candle.volume is not None
            else Decimal("0")
        )

        # --------------------------------------------------
        # Convert candle prices to Decimal
        # --------------------------------------------------

        high_price = self._to_decimal(
            candle.high_price
        )

        low_price = self._to_decimal(
            candle.low_price
        )

        close_price = self._to_decimal(
            candle.close_price
        )

        # --------------------------------------------------
        # Typical price
        # --------------------------------------------------

        typical_price = (
            high_price
            + low_price
            + close_price
        ) / Decimal("3")

        # --------------------------------------------------
        # Cumulative VWAP state
        # --------------------------------------------------

        cumulative = (
            self._vwap_data.setdefault(
                key,
                {
                    "price_volume": Decimal("0"),
                    "volume": Decimal("0")
                }
            )
        )

        # --------------------------------------------------
        # Accumulate price × volume
        # --------------------------------------------------

        cumulative["price_volume"] += (
            typical_price * volume
        )

        cumulative["volume"] += volume

        # --------------------------------------------------
        # Zero-volume candle
        # --------------------------------------------------

        if cumulative["volume"] == Decimal("0"):

            return typical_price

        # --------------------------------------------------
        # VWAP
        # --------------------------------------------------

        return (
            cumulative["price_volume"]
            / cumulative["volume"]
        )

    # ======================================================
    # RESET
    # ======================================================

    def reset(
        self,
        instrument_id: int,
        timeframe: str
    ) -> None:
        """
        Reset all indicator state for one
        instrument/timeframe combination.
        """

        key = (
            instrument_id,
            timeframe
        )

        # --------------------------------------------------
        # Previous close
        # --------------------------------------------------

        self._previous_close.pop(
            key,
            None
        )

        # --------------------------------------------------
        # EMA
        # --------------------------------------------------

        self._ema_9.pop(
            key,
            None
        )

        self._ema_20.pop(
            key,
            None
        )

        self._ema_50.pop(
            key,
            None
        )

        # --------------------------------------------------
        # MACD
        # --------------------------------------------------

        self._macd_ema_12.pop(
            key,
            None
        )

        self._macd_ema_26.pop(
            key,
            None
        )

        self._macd_signal.pop(
            key,
            None
        )

        # --------------------------------------------------
        # RSI
        # --------------------------------------------------

        self._rsi_gains.pop(
            key,
            None
        )

        self._rsi_losses.pop(
            key,
            None
        )

        # --------------------------------------------------
        # ATR
        # --------------------------------------------------

        self._atr_values.pop(
            key,
            None
        )

        # --------------------------------------------------
        # Volume
        # --------------------------------------------------

        self._volume_history.pop(
            key,
            None
        )

        # --------------------------------------------------
        # VWAP
        # --------------------------------------------------

        self._vwap_data.pop(
            key,
            None
        )

        # --------------------------------------------------
        # VWAP trading date
        # --------------------------------------------------

        self._vwap_date.pop(
            key,
            None
        )