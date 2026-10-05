import logging
from market_data.candle import Candle
import upstox_client
from datetime import datetime
from config.settings import Settings


class UpstoxHistoricalProvider:
    """
    Provides historical/intraday candle data from Upstox.
    """

    def __init__(self):

        self.logger = logging.getLogger(
            self.__class__.__name__
        )

        access_token = (
            Settings.UPSTOX_ACCESS_TOKEN
        )

        if not access_token:

            raise ValueError(
                "UPSTOX_ACCESS_TOKEN is not configured."
            )

        configuration = (
            upstox_client.Configuration()
        )

        configuration.access_token = (
            access_token
        )

        self.api_client = (
            upstox_client.ApiClient(
                configuration
            )
        )

        self.history_api = (
            upstox_client.HistoryV3Api(
                self.api_client
            )
        )

    def get_intraday_candles(
        self,
        instrument_key: str,
        interval: str = "1"
    ):

        response = (
            self.history_api.get_intra_day_candle_data(
                instrument_key,
                "minutes",
                interval
            )
        )

        return list(
            reversed(
                response.data.candles
            )
        )

    def get_intraday_candles_for_instruments(
        self,
        instrument_keys: list[str],
        interval: str = "1"
    ) -> dict[str, list]:
        """
        Fetch today's intraday candles for multiple instruments.

        Returns:
            {
                provider_instrument_id: candles
            }
        """

        results = {}

        for instrument_key in instrument_keys:

            self.logger.info(
                "Fetching historical candles | "
                f"instrument={instrument_key}"
            )

            candles = self.get_intraday_candles(
                instrument_key=instrument_key,
                interval=interval
            )

            results[instrument_key] = candles

        return results

    def convert_to_candles(
        self,
        instrument_id: int,
        candles: list,
        timeframe: str = "1m"
    ) -> list[Candle]:
        """
        Convert Upstox candle arrays into project Candle objects.
        """

        results = []

        for candle in candles:

            results.append(
                Candle(
                    instrument_id=instrument_id,
                    timestamp=datetime.fromisoformat(candle[0]),
                    timeframe=timeframe,
                    open_price=candle[1],
                    high_price=candle[2],
                    low_price=candle[3],
                    close_price=candle[4],
                    volume=candle[5]
                )
            )

        return results

if __name__ == "__main__":

    provider = UpstoxHistoricalProvider()

    raw_candles = provider.get_intraday_candles(
        instrument_key="NSE_EQ|INE002A01018",
        interval="1"
    )

    candles = provider.convert_to_candles(
        instrument_id=2,
        candles=raw_candles
    )

    print(f"Received {len(candles)} Candle objects")

    print(candles[0])
    print(candles[-1])

# if __name__ == "__main__":

#     provider = UpstoxHistoricalProvider()

#     results = provider.get_intraday_candles_for_instruments(
#         instrument_keys=[
#             "NSE_EQ|INE002A01018",
#             "NSE_EQ|INE040A01034"
#         ],
#         interval="1"
#     )

#     for instrument_key, candles in results.items():

#         print(
#             f"{instrument_key} -> "
#             f"{len(candles)} candles"
#         )

#         if candles:
#             print(
#                 f"First: {candles[0][0]}"
#             )
            
#             print(
#                 f"Last: {candles[-1][0]}"
#             )