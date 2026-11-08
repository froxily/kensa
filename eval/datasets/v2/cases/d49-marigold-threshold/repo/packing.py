def bucket_for(count: int) -> str:
    if count > 10:
        return "large"
    return "small"
