import pytest


@pytest.mark.parametrize("account", range(24))
def test_account_balance(db, account):
    with db.cursor() as cursor:
        cursor.execute("SELECT %s::integer", (account,))
        row = cursor.fetchone()
    assert row is not None
    assert row[0] == account
