from abc import ABC, abstractmethod
from typing import Callable, List

from market_data.models import MarketTick


class MarketDataProvider(ABC):
    """
    Abstract interface for all market-data providers.

    Any provider such as Upstox, Kite, Dhan, etc.
    must implement this interface.
    """

    def __init__(self):

        self._tick_callback = None
        self._failure_callback = None

    @abstractmethod
    def connect(self) -> None:
        """
        Establish connection with the market-data provider.
        """
        pass

    @abstractmethod
    def subscribe(
        self,
        instruments: List[str]
    ) -> None:
        """
        Subscribe to market-data instruments.
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """
        Close the provider connection.
        """
        pass

    def set_tick_callback(
        self,
        callback: Callable[[MarketTick], None]
    ) -> None:
        """
        Register a callback that receives normalized MarketTick objects.
        """

        self._tick_callback = callback

    def set_failure_callback(
        self,
        callback: Callable[[str], None]
    ) -> None:
        """
        Register a callback for unrecoverable provider failures.
        """

        self._failure_callback = callback

    def _emit_failure(
        self,
        message: str
    ) -> None:
        """
        Notify the registered callback of an unrecoverable provider failure.
        """
    
        if self._failure_callback is not None:
        
            self._failure_callback(
                message
            )

    def _emit_tick(
        self,
        tick: MarketTick
    ) -> None:
        """
        Send a normalized tick to the registered callback.
        """

        if self._tick_callback is not None:

            self._tick_callback(tick)