import gzip
import json
import logging
from typing import Dict, List

import requests

from database.connection import DatabaseConnection
from database.repository import InstrumentRepository


UPSTOX_NSE_INSTRUMENT_URL = (
    "https://assets.upstox.com/"
    "market-quote/instruments/exchange/NSE.json.gz"
)


class UpstoxInstrumentManager:
    """
    Downloads the public Upstox NSE instrument master
    and synchronizes selected NSE equity instruments
    with our PostgreSQL database.

    No Upstox access token is required for the instrument
    master file.
    """

    def __init__(self):

        self.db = DatabaseConnection()

        self.repository = InstrumentRepository(
            self.db
        )

    def download_instruments(self) -> List[Dict]:

        logging.info(
            "Downloading Upstox NSE instrument master..."
        )

        response = requests.get(
            UPSTOX_NSE_INSTRUMENT_URL,
            timeout=60
        )

        response.raise_for_status()

        logging.info(
            "Upstox instrument master downloaded."
        )

        content = gzip.decompress(
            response.content
        )

        instruments = json.loads(
            content.decode("utf-8")
        )

        logging.info(
            f"Total instruments received: "
            f"{len(instruments)}"
        )

        return instruments

    def get_equity_instruments(
        self,
        instruments: List[Dict]
    ) -> Dict[str, Dict]:

        equity_instruments = {}

        for instrument in instruments:

            if instrument.get("segment") != "NSE_EQ":
                continue

            instrument_type = instrument.get(
                "instrument_type"
            )

            if instrument_type not in {
                "EQ",
                "BE"
            }:
                continue

            trading_symbol = instrument.get(
                "trading_symbol"
            )

            if not trading_symbol:
                continue

            equity_instruments[
                trading_symbol.upper()
            ] = instrument

        logging.info(
            f"NSE equity instruments indexed: "
            f"{len(equity_instruments)}"
        )

        return equity_instruments

    def sync_symbols(
        self,
        symbols: List[str]
    ):

        instruments = self.download_instruments()

        equity_instruments = (
            self.get_equity_instruments(
                instruments
            )
        )

        matched = 0
        not_found = []

        for symbol in symbols:

            normalized_symbol = (
                symbol.strip().upper()
            )

            instrument = equity_instruments.get(
                normalized_symbol
            )

            if not instrument:

                not_found.append(
                    normalized_symbol
                )

                logging.warning(
                    f"Instrument not found: "
                    f"{normalized_symbol}"
                )

                continue

            instrument_id = (
                self.repository.upsert_instrument(
                    symbol=normalized_symbol,
                    exchange="NSE",
                    isin=instrument.get(
                        "isin",
                        ""
                    ),
                    provider="upstox",
                    provider_instrument_id=instrument.get(
                        "instrument_key"
                    ),
                    provider_symbol=instrument.get(
                        "trading_symbol"
                    )
                )
            )

            matched += 1

            logging.info(
                f"Mapped {normalized_symbol} "
                f"-> {instrument.get('instrument_key')} "
                f"(DB ID: {instrument_id})"
            )

        logging.info(
            f"Instrument synchronization completed. "
            f"Matched: {matched} | "
            f"Not found: {len(not_found)}"
        )

        if not_found:

            logging.warning(
                "Symbols not found: "
                + ", ".join(not_found)
            )

        return matched, not_found

    def close(self):

        self.db.close()