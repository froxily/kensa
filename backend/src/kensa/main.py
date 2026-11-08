"""ASGI entry point: ``uvicorn kensa.main:app --host 127.0.0.1``."""

from kensa.app import create_app

app = create_app()
