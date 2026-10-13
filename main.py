import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from config.settings import Settings

from market_data.market_data_service import (
    MarketDataService
)

from main2 import (
    recover_current_session
)


def wait_for_market_session() -> bool:

    timezone = ZoneInfo(
        Settings.MARKET_TIMEZONE
    )

    market_open = datetime.strptime(
        Settings.MARKET_OPEN,
        "%H:%M"
    ).time()

    market_close = datetime.strptime(
        Settings.MARKET_CLOSE,
        "%H:%M"
    ).time()

    logging.info(
        "Waiting for market session to start at "
        f"{Settings.MARKET_OPEN} IST."
    )

    while True:

        now = datetime.now(
            timezone
        )

        if now.time() >= market_close:

            logging.info(
                "Market session has already ended at "
                f"{Settings.MARKET_CLOSE} IST."
            )

            return False

        if now.time() >= market_open:

            logging.info(
                "Market session starting at "
                f"{Settings.MARKET_OPEN} IST."
            )

            return True

        time.sleep(1)


def main() -> None:

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "%(message)s"
        )
    )

    service = MarketDataService()

    try:

        if wait_for_market_session():

            logging.info(
                "Starting current-session data recovery."
            )

            recovery_results = (
                recover_current_session()
            )

            logging.info(
                "Startup recovery completed | "
                f"missing="
                f"{recovery_results['missing_candles']} | "
                f"recoverable="
                f"{recovery_results['recoverable_candles']} | "
                f"inserted="
                f"{recovery_results['candles_inserted']} | "
                f"skipped="
                f"{recovery_results['candles_skipped']} | "
                f"indicators="
                f"{recovery_results['indicators_processed']}"
            )

            logging.info(
                "Starting live market-data service."
            )

            service.start()

            wait_for_market_close()

    except KeyboardInterrupt:

        logging.info(
            "Shutdown requested by keyboard interrupt."
        )

    finally:

        service.stop()


def wait_for_market_close() -> None:

    timezone = ZoneInfo(
        Settings.MARKET_TIMEZONE
    )

    market_close = datetime.strptime(
        Settings.MARKET_CLOSE,
        "%H:%M"
    ).time()

    logging.info(
        "Market-data service running until "
        f"{Settings.MARKET_CLOSE} IST."
    )

    while True:

        now = datetime.now(
            timezone
        )

        if now.time() >= market_close:

            logging.info(
                "Market session ended at "
                f"{Settings.MARKET_CLOSE} IST."
            )

            return

        time.sleep(1)


if __name__ == "__main__":
    main()