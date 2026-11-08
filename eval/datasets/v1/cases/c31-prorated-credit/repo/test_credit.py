import pytest
from credit import credit_cents


def test_partial_month_credit():
    assert credit_cents(3000, 15, 30) == 1500


def test_full_month_credit():
    assert credit_cents(3000, 30, 30) == 3000


def test_rejects_negative_days():
    with pytest.raises(ValueError):
        credit_cents(3000, -1, 30)
