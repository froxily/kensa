def format_label(value):
    return value.strip().lower()


def test_trim():
    assert format_label(" Label ") == "label"


def test_lower():
    assert format_label("READY") == "ready"
