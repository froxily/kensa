import os

import psycopg


def test_database_version():
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        assert connection.execute("SELECT 1").fetchone() == (1,)
