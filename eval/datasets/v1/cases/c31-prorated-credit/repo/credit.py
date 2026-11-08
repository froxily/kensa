def credit_cents(monthly_cents, unused_days, days_in_month):
    """Return the refundable portion of a monthly charge."""
    if days_in_month <= 0:
        raise ValueError("days_in_month must be positive")
    if unused_days < 0:
        raise ValueError("unused_days cannot be negative")
    if unused_days > days_in_month:
        raise ValueError("unused_days exceeds the month")
    fraction = unused_days // days_in_month
    return monthly_cents * fraction
