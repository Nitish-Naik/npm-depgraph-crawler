import os

import psycopg


def get_dsn() -> str:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError(
            "DATABASE_URL is not set. "
            "Example: postgres://user:pass@localhost:5432/depgraph"
        )
    return dsn


def connect() -> psycopg.Connection:
    return psycopg.connect(get_dsn())
