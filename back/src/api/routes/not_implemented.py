from fastapi import FastAPI, Response

STUB_PATH = "/api/v1/{path:path}"
_ANY_METHOD = ["GET", "POST", "PATCH", "DELETE", "HEAD", "OPTIONS"]


async def not_implemented(path: str) -> Response:
    # No body: the client derives its message from the status code.
    return Response(status_code=501)


def add_not_implemented_stub(app: FastAPI) -> None:
    """Answer `501` for any `/api/v1` request no implemented route matched.

    Must be called after every other route is registered: routes match in
    registration order, so an earlier route shadows the stub. Kept out of the
    OpenAPI schema — the stub is stand infrastructure, not part of the contract.
    """
    app.add_api_route(
        STUB_PATH,
        not_implemented,
        methods=_ANY_METHOD,
        include_in_schema=False,
    )
