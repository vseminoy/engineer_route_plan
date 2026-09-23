import json
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.types import Message, Receive, Scope, Send

from src.api.body_limit import BodyLimitMiddleware
from src.app import create_app
from src.config import Settings

LIMIT = 1024


class _ReadingApp:
    """Reads the whole body, counting what `receive` hands over, then answers 200."""

    def __init__(self, respond_first: bool = False) -> None:
        self.called = False
        self.received = 0
        self.receive_calls = 0
        self.respond_first = respond_first
        self.scope_type: str | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.called = True
        self.scope_type = scope["type"]
        if scope["type"] != "http":
            return
        if self.respond_first:
            await send({"type": "http.response.start", "status": 200, "headers": []})
        more = True
        while more:
            message = await receive()
            self.received += len(message.get("body", b""))
            more = message.get("more_body", False)
        if not self.respond_first:
            await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


async def _call(
    app: _ReadingApp, headers: list[tuple[bytes, bytes]], chunks: list[bytes], method: str = "POST"
) -> list[Message]:
    pending = list(chunks) or [b""]

    async def receive() -> Message:
        app.receive_calls += 1
        body = pending.pop(0) if pending else b""
        return {"type": "http.request", "body": body, "more_body": bool(pending)}

    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    scope = {"type": "http", "method": method, "path": "/", "headers": headers}
    await BodyLimitMiddleware(app, max_bytes=LIMIT)(scope, receive, send)
    return sent


def _status(sent: list[Message]) -> list[int]:
    return [m["status"] for m in sent if m["type"] == "http.response.start"]


def _body(sent: list[Message]) -> bytes:
    return b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")


def _chunks(total: int, size: int = 512) -> list[bytes]:
    return [b"x" * min(size, total - i) for i in range(0, total, size)]


def _length(n: int | str) -> list[tuple[bytes, bytes]]:
    return [(b"content-length", str(n).encode())]


async def test_content_length_over_limit_rejected_without_reading() -> None:
    app = _ReadingApp()
    sent = await _call(app, _length(LIMIT + 1), [b"x" * (LIMIT + 1)])

    assert _status(sent) == [413]
    assert _body(sent) == b""
    (start,) = [m for m in sent if m["type"] == "http.response.start"]
    assert (b"content-length", b"0") in start["headers"]
    assert (b"connection", b"close") in start["headers"]
    assert not app.called
    assert app.receive_calls == 0


async def test_content_length_at_limit_passes() -> None:
    app = _ReadingApp()
    sent = await _call(app, _length(LIMIT), [b"x" * LIMIT])

    assert _status(sent) == [200]
    assert app.received == LIMIT


async def test_chunked_body_over_limit_rejected_while_reading() -> None:
    app = _ReadingApp()
    sent = await _call(app, [], _chunks(2048))

    assert _status(sent) == [413]
    assert _body(sent) == b""
    assert app.received <= LIMIT


async def test_chunked_body_under_limit_passes() -> None:
    app = _ReadingApp()
    sent = await _call(app, [], _chunks(1000))

    assert _status(sent) == [200]
    assert app.received == 1000


async def test_invalid_content_length_falls_back_to_counting() -> None:
    app = _ReadingApp()
    sent = await _call(app, _length("abc"), _chunks(2048))

    assert _status(sent) == [413]


async def test_request_without_body_passes() -> None:
    app = _ReadingApp()
    sent = await _call(app, [], [], method="GET")

    assert _status(sent) == [200]


async def test_over_limit_after_response_started_does_not_send_second_response() -> None:
    app = _ReadingApp(respond_first=True)
    sent = await _call(app, [], _chunks(2048))

    assert _status(sent) == [200]
    assert app.received <= LIMIT


async def test_non_http_scope_passes_through() -> None:
    app = _ReadingApp()

    async def receive() -> Message:
        return {"type": "lifespan.startup"}

    async def send(message: Message) -> None:
        pass

    await BodyLimitMiddleware(app, max_bytes=LIMIT)({"type": "lifespan"}, receive, send)

    assert app.scope_type == "lifespan"


class _Payload(BaseModel):
    data: str


def _app_with_json_route() -> FastAPI:
    settings = Settings(
        database_url="postgresql://test/test",
        osrm_url="http://osrm.test",
        max_request_body_bytes=LIMIT,
    )
    app = create_app(settings=settings)

    @app.post("/t/payload")
    async def post_payload(body: _Payload) -> None:
        return None

    return app


def _stream(total: int) -> Iterator[bytes]:
    # A generator body makes the client send it chunked, without `Content-Length`.
    yield b'{"data": "'
    yield from _chunks(total)
    yield b'"}'


@pytest.mark.parametrize("chunked", [False, True], ids=["content_length", "chunked"])
def test_413_through_app_has_request_id_and_is_logged(
    capsys: pytest.CaptureFixture[str], chunked: bool
) -> None:
    # The app is built inside the test: its log handler binds the stderr that is
    # current at that moment, which must already be the captured one.
    with TestClient(_app_with_json_route()) as client:
        body = _stream(2048) if chunked else b"x" * 2048
        response = client.post(
            "/t/payload", content=body, headers={"content-type": "application/json"}
        )

    assert response.status_code == 413
    assert response.content == b""
    assert response.headers["content-length"] == "0"
    assert response.headers["connection"] == "close"
    assert response.headers["x-request-id"]
    lines = [line for line in capsys.readouterr().err.splitlines() if line.startswith("{")]
    finished = [e for e in map(json.loads, lines) if e["event"] == "http_request_finished"]
    assert [e["status"] for e in finished] == [413]
