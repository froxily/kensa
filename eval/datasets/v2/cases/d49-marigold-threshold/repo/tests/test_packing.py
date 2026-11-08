import pytest
from packing import bucket_for


@pytest.mark.parametrize("count", [0, 1, 2, 3, 4, 5, 6, 7, 8])
def test_small_counts(count):
    assert bucket_for(count) == "small"


def test_ten_items_are_large():
    assert bucket_for(10) == "large"
