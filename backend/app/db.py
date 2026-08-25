"""
Talking to Postgres.

I am using psycopg2 directly instead of an ORM. The whole point of this
project is one careful SQL query, the eligibility filter in
eligibility.py, and I would rather write and read that query as SQL than
hide it behind a query builder and then have to explain what it turns
into.

Every function here opens a connection, does its work, and closes it in
a finally block.

That finally block is not decoration. I wrote this the short way first:

    with get_connection() as connection:
        ...

and ingestion hung on the very first document. `with` on a psycopg2
connection commits the transaction, but it does **not** close the
connection, which is not what the same syntax does for a file. So every
insert left a connection open, and a few hundred inserts later Postgres
hit max_connections and simply stopped answering. Closing has to be
explicit.
"""

import psycopg2
from psycopg2.extras import RealDictCursor

from . import config


def get_connection():
    """One new connection to Postgres."""
    return psycopg2.connect(
        dbname=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        host=config.DB_HOST,
        port=config.DB_PORT,
    )


def _run(sql, params, fetch):
    """
    Run one statement and always close the connection afterwards.

    fetch is "all", "one" or None. Everything else in this file is a
    thin wrapper around this, so the closing only has to be right once.
    """
    connection = get_connection()
    try:
        # RealDictCursor gives row["name"] instead of row[1]. Worth it,
        # because a query with twelve columns is unreadable by number.
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            # params has to be None, not an empty dict. Given a dict,
            # psycopg2 treats every % in the SQL as a placeholder, so a
            # query holding LIKE 'Mukhyamantri%' fails with a message
            # about sequences that says nothing about the real problem.
            cursor.execute(sql, params if params else None)

            result = None
            if fetch == "all":
                result = [dict(row) for row in cursor.fetchall()]
            elif fetch == "one":
                row = cursor.fetchone()
                result = dict(row) if row else None

        connection.commit()
        return result
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def fetch_all(sql, params=None):
    """Run a SELECT and give back a list of dictionaries."""
    return _run(sql, params, fetch="all")


def fetch_one(sql, params=None):
    """Run a SELECT that should return one row. None if there is no row."""
    return _run(sql, params, fetch="one")


def execute(sql, params=None):
    """Run an INSERT, UPDATE or DELETE that returns nothing."""
    _run(sql, params, fetch=None)


def insert_returning_id(sql, params=None):
    """
    Run an INSERT that ends with RETURNING id and give the id back.

    Used all through ingestion, because a scheme has to exist before its
    criteria row and its chunks can point at it.
    """
    row = _run(sql, params, fetch="one")
    return row["id"]


def run_script(path):
    """Run a whole .sql file. Only used for schema.sql."""
    sql = path.read_text(encoding="utf-8")
    _run(sql, None, fetch=None)


def execute_many(statements):
    """
    Run several statements on one connection.

    Ingestion writes a scheme, its criteria and half a dozen chunks in a
    row. Doing that through execute() means a new connection each time,
    which works but is wasteful, so the chunk inserts come through here.

    statements is a list of (sql, params) pairs. They all commit
    together or none of them do.
    """
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            for sql, params in statements:
                cursor.execute(sql, params if params else None)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
