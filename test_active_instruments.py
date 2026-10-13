from database.connection import DatabaseConnection
from database.repository import InstrumentRepository


def main():

    db = DatabaseConnection()

    repository = InstrumentRepository(
        db
    )

    try:

        instruments = (
            repository
            .get_active_provider_instrument_ids()
        )

        print(
            f"Active instruments found: "
            f"{len(instruments)}"
        )

        for instrument in instruments:

            print(instrument)

    finally:

        db.close()


if __name__ == "__main__":

    main()