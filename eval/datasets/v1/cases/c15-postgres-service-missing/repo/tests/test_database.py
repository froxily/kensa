import os
import psycopg

def test_inventory_database():
    with psycopg.connect(os.environ['DATABASE_URL'], connect_timeout=3) as conn:
        with conn.cursor() as cursor:
            cursor.execute('SELECT 1')
            assert cursor.fetchone() == (1,)

# The integration check requires a running PostgreSQL server.
