from marsh_store import open_marsh

with open_marsh() as connection:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        assert cursor.fetchone() == (1,)
print("query passed")
