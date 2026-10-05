import logging
from typing import List

import pandas as pd

from market_data.instrument_master import (
    UpstoxInstrumentMaster
)

from market_data.instrument_matcher import (
    InstrumentMatcher
)

from database.repository import (
    InstrumentRepository
)


class InstrumentSyncService:
    """
    Synchronizes the NSE F&O universe with PostgreSQL.

    Flow:

        NSE F&O DataFrame
                ↓
        NSE symbols
                ↓
        InstrumentMatcher
                ↓
        Verified Upstox instruments
                ↓
        InstrumentRepository
                ↓
        PostgreSQL instruments
    """

    def __init__(
        self,
        instrument_repository: InstrumentRepository
    ):

        self.instrument_repository = (
            instrument_repository
        )

        self.instrument_master = (
            UpstoxInstrumentMaster()
        )

        self.logger = logging.getLogger(
            self.__class__.__name__
        )

    # --------------------------------------------------
    # Synchronization
    # --------------------------------------------------

    def sync(
        self,
        nse_df: pd.DataFrame
    ) -> None:
        """
        Match the authoritative NSE F&O universe against
        the Upstox instrument master and synchronize the
        verified instruments into PostgreSQL.

        The DataFrame must contain a 'Symbol' column.
        """

        if "Symbol" not in nse_df.columns:

            raise ValueError(
                "NSE F&O DataFrame must contain "
                "a 'Symbol' column."
            )

        nse_symbols: List[str] = (
            nse_df["Symbol"]
            .dropna()
            .astype(str)
            .str.strip()
            .tolist()
        )

        self.logger.info(
            f"NSE F&O instruments received: "
            f"{len(nse_symbols)}"
        )

        if not nse_symbols:

            self.logger.warning(
                "No NSE F&O instruments supplied."
            )

            return

        # --------------------------------------------------
        # Load Upstox instrument master
        # --------------------------------------------------

        self.logger.info(
            "Loading Upstox NSE equity instrument master..."
        )

        upstox_instruments = (
            self.instrument_master.get_nse_equities()
        )

        self.logger.info(
            "Upstox NSE equity instruments available: "
            f"{len(upstox_instruments)}"
        )

        # --------------------------------------------------
        # Match
        # --------------------------------------------------

        matcher = InstrumentMatcher(
            upstox_instruments
        )

        results = matcher.match_all(
            nse_symbols
        )

        # --------------------------------------------------
        # Categorize results
        # --------------------------------------------------

        matched = [
            result
            for result in results
            if result["status"] == "matched"
        ]

        ambiguous = [
            result
            for result in results
            if result["status"] == "ambiguous"
        ]

        unmatched = [
            result
            for result in results
            if result["status"] == "unmatched"
        ]

        # --------------------------------------------------
        # Summary
        # --------------------------------------------------

        self.logger.info(
            "Instrument matching completed: "
            f"matched={len(matched)}, "
            f"ambiguous={len(ambiguous)}, "
            f"unmatched={len(unmatched)}"
        )

        # --------------------------------------------------
        # Never write incomplete universe
        # --------------------------------------------------

        if ambiguous or unmatched:

            matcher.print_unmatched(
                results
            )

            matcher.print_ambiguous(
                results
            )

            raise RuntimeError(
                "Instrument synchronization aborted. "
                f"Ambiguous={len(ambiguous)}, "
                f"Unmatched={len(unmatched)}. "
                "All NSE F&O symbols must have "
                "a unique Upstox match."
                "a unique Upstox match before synchronization."
            )

        # --------------------------------------------------
        # Synchronize
        # --------------------------------------------------

        synchronized = 0

        for result in matched:

            instrument = result[
                "instrument"
            ]

            trading_symbol = (
                instrument.get(
                    "trading_symbol"
                )
            )

            isin = (
                instrument.get(
                    "isin"
                )
            )

            instrument_key = (
                instrument.get(
                    "instrument_key"
                )
            )

            if not trading_symbol:

                raise ValueError(
                    "Matched Upstox instrument has "
                    "no trading_symbol."
                )

            if not instrument_key:

                raise ValueError(
                    "Matched Upstox instrument has "
                    "no instrument_key."
                )

            self.instrument_repository.upsert_instrument(
                symbol=trading_symbol,
                exchange="NSE",
                isin=isin,
                provider="UPSTOX",
                provider_instrument_id=instrument_key,
                provider_symbol=trading_symbol
            )

            synchronized += 1

        self.logger.info(
            "Instrument synchronization completed: "
            f"{synchronized} instruments synchronized."
        )