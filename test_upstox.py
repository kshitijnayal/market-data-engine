import logging
import time

from database.connection import DatabaseConnection
from database.repository import InstrumentRepository
from database.repository import TickRepository
from market_data.upstox_provider import UpstoxProvider


logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(message)s"
    ),
    handlers=[
        logging.StreamHandler()
    ]
)

def main():

    db = DatabaseConnection()
    instrument_repository = InstrumentRepository(
        db
    )   

    repository = TickRepository(
        db
    )
    instruments = (
        instrument_repository
        .get_active_provider_instrument_ids()
    )

    if not instruments:

        logging.error(
            "No active instruments found in database."
        )

        db.close()

        return

    logging.info(
        f"Loaded {len(instruments)} active instruments "
        f"from PostgreSQL."
    )

    provider = UpstoxProvider(
        instrument_keys=instruments,
        mode="full",
        instrument_repository=instrument_repository
    )

    tick_count = 0

    def handle_tick(tick):

        nonlocal tick_count

        tick_count += 1

        logging.info(
            "LIVE TICK | "
            f"Instrument ID: {tick.instrument_id} | "
            f"Price: {tick.last_price} | "
            f"Volume: {tick.volume}"
        )

        repository.save_tick(
            tick
        )

    provider.set_tick_callback(
        handle_tick
    )

    try:

        logging.info(
            "Starting Upstox live market-data test..."
        )

        provider.connect()

        # Keep the program alive.
        #
        # The WebSocket runs asynchronously and
        # invokes handle_tick() whenever data arrives.

        while True:

            time.sleep(1)

    except KeyboardInterrupt:

        logging.info(
            "Stopping live market-data test..."
        )

    finally:

        provider.disconnect()

        db.close()

        logging.info(
            f"Total ticks received: "
            f"{tick_count}"
        )


if __name__ == "__main__":

    main()