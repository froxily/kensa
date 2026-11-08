"""Status responses for the service."""


def status():
    """Return a minimal health response."""
    return {
        "status": "ok",
        "service": "quartz",
    }

