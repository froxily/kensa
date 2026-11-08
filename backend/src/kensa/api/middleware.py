"""ASGI middleware."""

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

UNSAFE_METHODS = frozenset({b"POST", b"PUT", b"PATCH", b"DELETE"})


class RequireJsonMiddleware:
    """State-changing API requests must declare ``Content-Type: application/json`` (415
    otherwise). A cross-site page can only send such a request after a CORS preflight, which
    fails for any origin but the Kensa UI, so forms or plain ``fetch`` calls from other sites
    cannot trigger actions (CSRF), including body-less ones such as ``/retry``."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"].encode() in UNSAFE_METHODS:
            headers = dict(scope.get("headers") or [])
            content_type = headers.get(b"content-type", b"").split(b";")[0].strip().lower()
            if content_type != b"application/json":
                body = json.dumps({"detail": "Send JSON (Content-Type: application/json)."})
                await send(
                    {
                        "type": "http.response.start",
                        "status": 415,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body.encode()})
                return
        await self.app(scope, receive, send)


class _BodyTooLargeError(Exception):
    pass


class BodySizeLimitMiddleware:
    """Rejects requests whose body exceeds ``max_bytes`` with 413, using Content-Length when
    present and counting streamed bytes otherwise, so oversized uploads are never buffered."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def _reject(self, send: Send) -> None:
        body = json.dumps({"detail": f"Request body exceeds {self.max_bytes} bytes."}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    too_large = int(value) > self.max_bytes
                except ValueError:
                    too_large = True
                if too_large:
                    await self._reject(send)
                    return

        received = 0
        started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLargeError
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLargeError:
            if not started:
                await self._reject(send)
