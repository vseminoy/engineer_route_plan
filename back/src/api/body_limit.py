"""Rejects request bodies larger than the configured limit with `413`, no body.

Pure ASGI rather than `BaseHTTPMiddleware`: the limit is enforced on the
`receive` stream, so an oversized body is never read into memory in full.
"""

from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class _BodyTooLarge(HTTPException):
    """Raised from `receive` once the body passes the limit.

    An `HTTPException`, because FastAPI re-raises that type from body parsing
    instead of turning it into a `400`; the error handlers then answer `413`.
    Source: fastapi/routing.py, `get_request_handler` (`except HTTPException: raise`).
    """

    def __init__(self) -> None:
        super().__init__(status_code=413, headers=_CLOSE)


# The unread rest of the body would otherwise keep arriving on this connection.
_CLOSE = {"Connection": "close"}


def _content_length(scope: Scope) -> int | None:
    for name, value in scope["headers"]:
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                # Unparseable: the body is counted while it is read instead.
                return None
    return None


async def _send_413(send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-length", b"0"), (b"connection", b"close")],
        }
    )
    await send({"type": "http.response.body", "body": b""})


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = _content_length(scope)
        if declared is not None and declared > self.max_bytes:
            await _send_413(send)
            return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLarge()
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge:
            # Reaches here only when no error handler answered it (inside FastAPI
            # the handlers turn it into the `413`). Once a response has started,
            # a second one cannot be sent; the connection is simply ended.
            if not response_started:
                await _send_413(send)
