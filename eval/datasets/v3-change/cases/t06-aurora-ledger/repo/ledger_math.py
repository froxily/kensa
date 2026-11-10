def outstanding(entries):
    """Total signed amounts for entries that are still open."""
    return sum(abs(entry["amount"]) for entry in entries if not entry["settled"])
