import os

import psycopg


def configured() -> bool:
    return bool(os.environ.get("DATABASE_URL"))


def connect() -> psycopg.Connection:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(dsn, connect_timeout=15)
