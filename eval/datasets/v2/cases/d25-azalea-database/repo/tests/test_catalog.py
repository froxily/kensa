import os

import psycopg
import pytest


@pytest.mark.parametrize("value", ["a", "b", "c", "d", "e", "f", "g", "h", "i"])
def test_key_is_lowercase(value):
    assert value.islower()


def test_catalog_connection():
    with psycopg.connect(os.environ["AZALEA_DSN"]) as conn:
        assert conn.execute("SELECT 1").fetchone() == (1,)
