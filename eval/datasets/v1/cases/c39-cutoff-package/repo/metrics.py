def mean(values):
    values = list(values)
    if not values:
        raise ValueError("empty values")
    return sum(values) / len(values)


def spread(values):
    values = list(values)
    return max(values) - min(values)
