from database.connection import DatabaseConnection


def main():

    db = DatabaseConnection()

    try:

        connection = db.connect()

        print(
            "PostgreSQL connection successful!"
        )

        cursor = connection.cursor()

        cursor.execute(
            "SELECT version();"
        )

        version = cursor.fetchone()

        print(
            f"PostgreSQL version: {version[0]}"
        )

        cursor.close()

    except Exception as error:

        print(
            f"Database connection failed: {error}"
        )

    finally:

        db.close()


if __name__ == "__main__":
    main()