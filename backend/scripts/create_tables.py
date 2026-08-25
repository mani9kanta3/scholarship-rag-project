"""
Create the database and all the tables.

Run this once, before anything else:

    python -m scripts.create_tables

It is safe to run again. Creating the database is skipped if it is
already there, and every table in schema.sql uses IF NOT EXISTS.

    python -m scripts.create_tables --reset

drops every table first. I need this while the schema is still moving,
because IF NOT EXISTS will not add a column to a table that already
exists, so a changed schema.sql would otherwise do nothing at all and
leave me wondering why.
"""

import sys

import psycopg2
from psycopg2 import sql

from app import config, db

# Children first, so a foreign key never blocks the drop.
TABLES = [
    "query_log",
    "eval_run",
    "eval_question",
    "document_chunk",
    "eligibility_criteria",
    "scheme",
]


def create_database_if_missing():
    """
    A connection has to name a database, and the one we want does not
    exist yet. So this connects to the built in "postgres" database
    first and creates ours from there.
    """
    connection = psycopg2.connect(
        dbname="postgres",
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        host=config.DB_HOST,
        port=config.DB_PORT,
    )
    # CREATE DATABASE cannot run inside a transaction, and psycopg2 opens
    # one for me automatically. autocommit turns that off.
    connection.autocommit = True

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (config.DB_NAME,),
        )
        if cursor.fetchone():
            print(f"Database {config.DB_NAME} is already there.")
        else:
            # The database name cannot be passed as a normal parameter,
            # so sql.Identifier quotes it properly instead.
            cursor.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(config.DB_NAME))
            )
            print(f"Created database {config.DB_NAME}.")

    connection.close()


def drop_all_tables():
    """Throw every table away. Only when --reset is passed."""
    for table in TABLES:
        db.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    print("Dropped all tables.")


def main():
    create_database_if_missing()

    if "--reset" in sys.argv:
        drop_all_tables()

    schema_file = config.BASE_DIR / "backend" / "app" / "schema.sql"
    db.run_script(schema_file)
    print("Tables are ready.")

    tables = db.fetch_all(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
        """
    )
    for table in tables:
        print("  -", table["table_name"])


if __name__ == "__main__":
    main()
