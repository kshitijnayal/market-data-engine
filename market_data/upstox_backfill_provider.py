import logging
from datetime import datetime, timedelta

import upstox_client

from config.settings import Settings


class UpstoxBackfillProvider:
    """
    Provides historical candle data from Upstox
    for long-range database backfills.
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

    # --------------------------------------------------
    # Fetch one historical date range
    # --------------------------------------------------

    def get_historical_candles(
        self,
        instrument_key: str,
        start_date: str,
        end_date: str,
        interval: str = "1"
    ) -> list:
        """
        Fetch historical 1-minute candles for an
        instrument between two dates.

        Dates must use:

            YYYY-MM-DD

        Upstox historical API has a limited maximum
        date range for intraday intervals, so this
        method splits larger ranges into smaller
        chunks.
        """

        start = datetime.strptime(
            start_date,
            "%Y-%m-%d"
        ).date()

        end = datetime.strptime(
            end_date,
            "%Y-%m-%d"
        ).date()

        if end < start:

            raise ValueError(
                "end_date cannot be earlier than start_date."
            )

        all_candles = []

        current_start = start

        while current_start <= end:

            current_end = min(
                current_start + timedelta(days=28),
                end
            )

            self.logger.info(
                "Fetching historical candles | "
                f"instrument={instrument_key} | "
                f"start={current_start} | "
                f"end={current_end}"
            )

            response = (
                self.history_api
                .get_historical_candle_data1(
                    instrument_key,
                    "minutes",
                    interval,
                    current_end.strftime(
                        "%Y-%m-%d"
                    ),
                    current_start.strftime(
                        "%Y-%m-%d"
                    )
                )
            )

            candles = list(
                reversed(
                    response.data.candles
                )
            )

            all_candles.extend(
                candles
            )

            current_start = (
                current_end + timedelta(days=1)
            )

        return all_candles
