import os

import psycopg
import pytest


@pytest.fixture
def db():
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=2) as conn:
        yield conn
        conn.rollback()
