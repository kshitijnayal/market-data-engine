import logging
from typing import Dict, List


class InstrumentMatcher:
    """
    Matches authoritative NSE F&O symbols against the
    Upstox NSE equity instrument master.

    Matching strategy:

        NSE F&O Symbol
              ↓
        Exact Upstox trading_symbol
              ↓
        Unique match

    No fuzzy matching.
    No aliases.
    No company-name matching.

    This is intentional because the NSE F&O universe is now
    the authoritative source for which instruments we want.
    """

    def __init__(
        self,
        instruments: List[Dict]
    ):

        self.instruments = instruments

        self.logger = logging.getLogger(
            self.__class__.__name__
        )

        # --------------------------------------------------
        # Build exact trading-symbol index
        # --------------------------------------------------

        self.symbol_index = {}

        for instrument in self.instruments:

            trading_symbol = (
                instrument.get(
                    "trading_symbol"
                )
                or ""
            ).strip().upper()

            if not trading_symbol:
                continue

            self.symbol_index.setdefault(
                trading_symbol,
                []
            ).append(instrument)

    # --------------------------------------------------
    # Match one NSE symbol
    # --------------------------------------------------

    def match(
        self,
        nse_symbol: str
    ) -> Dict:
        """
        Match one authoritative NSE F&O symbol against
        the Upstox NSE equity instrument master.
        """

        symbol = (
            nse_symbol
            or ""
        ).strip().upper()

        if not symbol:

            return {
                "status": "unmatched",
                "nse_symbol": nse_symbol,
                "instrument": None,
                "reason": "Empty NSE symbol"
            }

        matches = self.symbol_index.get(
            symbol,
            []
        )

        # --------------------------------------------------
        # Exactly one match
        # --------------------------------------------------

        if len(matches) == 1:

            return {
                "status": "matched",
                "nse_symbol": nse_symbol,
                "instrument": matches[0],
                "reason": (
                    "Exact NSE symbol -> "
                    "Upstox trading symbol match"
                )
            }

        # --------------------------------------------------
        # Multiple matches
        # --------------------------------------------------

        if len(matches) > 1:

            return {
                "status": "ambiguous",
                "nse_symbol": nse_symbol,
                "instrument": matches,
                "reason": (
                    "Multiple Upstox instruments "
                    "with same trading symbol"
                )
            }

        # --------------------------------------------------
        # No match
        # --------------------------------------------------

        return {
            "status": "unmatched",
            "nse_symbol": nse_symbol,
            "instrument": None,
            "reason": (
                "NSE symbol not found in "
                "Upstox NSE equity master"
            )
        }

    # --------------------------------------------------
    # Match complete NSE F&O universe
    # --------------------------------------------------

    def match_all(
        self,
        nse_symbols: List[str]
    ) -> List[Dict]:
        """
        Match the complete NSE F&O symbol universe.
        """

        results = []

        for symbol in nse_symbols:

            result = self.match(
                symbol
            )

            results.append(
                result
            )

            self.logger.info(
                f"{symbol} -> "
                f"{result['status']} | "
                f"{result['reason']}"
            )

        return results

    # --------------------------------------------------
    # Diagnostic candidate lookup
    # --------------------------------------------------

    def find_candidates(
        self,
        nse_symbol: str
    ) -> List[Dict]:
        """
        Diagnostic helper.

        Since matching is intentionally exact, this only
        returns exact trading-symbol candidates.
        """

        symbol = (
            nse_symbol
            or ""
        ).strip().upper()

        return self.symbol_index.get(
            symbol,
            []
        )