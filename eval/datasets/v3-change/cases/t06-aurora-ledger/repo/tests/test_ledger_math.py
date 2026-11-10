from ledger_math import outstanding


def test_outstanding_nets_credits():
    entries = [
        {"amount": 90, "settled": False},
        {"amount": -25, "settled": False},
        {"amount": 10, "settled": True},
    ]
    assert outstanding(entries) == 65


def test_outstanding_empty():
    assert outstanding([]) == 0
