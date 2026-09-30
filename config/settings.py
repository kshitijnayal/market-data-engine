import os

from dotenv import load_dotenv


load_dotenv()


class Settings:

    # --------------------------------------------------
    # Upstox
    # --------------------------------------------------

    UPSTOX_ACCESS_TOKEN = os.getenv(
        "UPSTOX_ACCESS_TOKEN"
    )

    # --------------------------------------------------
    # PostgreSQL
    # --------------------------------------------------

    DB_HOST = os.getenv(
        "DB_HOST",
        "localhost"
    )

    DB_PORT = int(
        os.getenv(
            "DB_PORT",
            "5432"
        )
    )

    DB_NAME = os.getenv(
        "DB_NAME",
        "exafinvest_market"
    )

    DB_USER = os.getenv(
        "DB_USER",
        "postgres"
    )

    DB_PASSWORD = os.getenv(
        "DB_PASSWORD"
    )

    # --------------------------------------------------
    # Market session
    # --------------------------------------------------

    MARKET_TIMEZONE = "Asia/Kolkata"

    MARKET_OPEN = "09:15"

    MARKET_CLOSE = "15:30"