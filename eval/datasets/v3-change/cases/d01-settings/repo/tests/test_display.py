from src.display import label
from src.settings import REGION


def test_label():
    assert label("  pear  ") == "Pear"
    assert REGION
