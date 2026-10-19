import os
from contextlib import contextmanager

import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row


def database_url():
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        password = os.getenv("POSTGRES_PASSWORD", "")
        if not password:
            raise RuntimeError("Set POSTGRES_PASSWORD for Docker or DATABASE_URL for an existing database")
        return make_conninfo(
            host=os.getenv("DATABASE_HOST", "127.0.0.1").strip() or "127.0.0.1",
            port=os.getenv("DATABASE_PORT", "5432").strip() or "5432",
            user=os.getenv("POSTGRES_USER", "chatbot").strip() or "chatbot",
            password=password,
            dbname=os.getenv("POSTGRES_DB", "chatbot").strip() or "chatbot",
        )
    overrides = {
        key: value
        for key, variable in (("host", "DATABASE_HOST"), ("port", "DATABASE_PORT"))
        if (value := os.getenv(variable, "").strip())
    }
    return make_conninfo(url, **overrides) if overrides else url


@contextmanager
def connection():
    with psycopg.connect(database_url(), row_factory=dict_row, connect_timeout=5) as conn:
        yield conn
