def active_slots(start, end):
    """Count whole slots in the half-open interval."""
    if end <= start:
        return 0
    return end - start + 1
