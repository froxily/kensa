import os
import psycopg


def connect():
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        dbname=os.getenv("DB_NAME", "catalog_test"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        connect_timeout=5,
    )


def test_connection():
    with connect() as conn:
        assert conn.execute("SELECT 1").fetchone() == (1,)
