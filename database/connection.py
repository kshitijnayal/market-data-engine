import psycopg2

from config.settings import Settings


class DatabaseConnection:

    def __init__(self):

        self.connection = None

    def connect(self):

        if self.connection is not None:
            return self.connection

        self.connection = psycopg2.connect(
            host=Settings.DB_HOST,
            port=Settings.DB_PORT,
            database=Settings.DB_NAME,
            user=Settings.DB_USER,
            password=Settings.DB_PASSWORD
        )

        return self.connection

    def close(self):

        if self.connection is not None:

            self.connection.close()

            self.connection = None