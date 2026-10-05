import logging
from typing import Dict, List

import requests


class UpstoxInstrumentMaster:
    """
    Downloads and processes the official Upstox
    NSE instrument master.

    Responsibilities:
        1. Download Upstox NSE instrument JSON.
        2. Filter NSE equity instruments.
        3. Provide instrument records for matching.

    This class does NOT interact with PostgreSQL.
    """

    # --------------------------------------------------
    # Configuration
    # --------------------------------------------------

    # Official Upstox NSE instrument JSON file.
    INSTRUMENT_URL = (
        "https://assets.upstox.com/"
        "market-quote/instruments/exchange/"
        "NSE.json.gz"
    )

    def __init__(self):

        self.logger = logging.getLogger(
            self.__class__.__name__
        )

    # --------------------------------------------------
    # Download
    # --------------------------------------------------

    def download(self) -> List[Dict]:

        self.logger.info(
            "Downloading Upstox NSE instrument master..."
        )

        response = requests.get(
            self.INSTRUMENT_URL,
            timeout=60
        )

        response.raise_for_status()

        self.logger.info(
            "Upstox NSE instrument master "
            "downloaded successfully."
        )

        return self._parse_response(
            response
        )

    # --------------------------------------------------
    # Parse
    # --------------------------------------------------

    @staticmethod
    def _parse_response(
        response: requests.Response
    ) -> List[Dict]:

        import gzip
        import json

        content = gzip.decompress(
            response.content
        )

        return json.loads(
            content.decode("utf-8")
        )

    # --------------------------------------------------
    # NSE Equity Filter
    # --------------------------------------------------

    def get_nse_equities(
        self
    ) -> List[Dict]:

        instruments = self.download()

        equities = [
            instrument
            for instrument in instruments
            if instrument.get("segment") == "NSE_EQ"
            and instrument.get("instrument_type") == "EQ"
        ]

        self.logger.info(
            f"NSE equity instruments found: "
            f"{len(equities)}"
        )

        return equities