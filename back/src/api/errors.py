"""Maps exceptions to HTTP responses. The only place an error response is built.

Only `400` carries a body; every other error status is sent without one, and the
client words the message from the operation and the status.
"""

from collections.abc import Mapping, Sequence
from typing import cast

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic_core import ErrorDetails
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.schemas.generated.common import (
    FieldError,
    FieldErrors,
    RequestMessage,
    ValidationError,
)
from src.errors import AppError, Conflict, DependencyUnavailable, InvalidInput, NotFound
from src.logging import get_logger

logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"

# Checked in order with `isinstance`, so a domain subclass (`PlanNotFound(NotFound)`)
# gets its base class's status. `InvalidInput` is answered separately, with a body.
_STATUS_BY_ERROR: tuple[tuple[type[AppError], int], ...] = (
    (NotFound, 404),
    (Conflict, 409),
    (DependencyUnavailable, 503),
)

# `loc` of a Pydantic error starts with where the value came from; the contract
# names the parameter without it.
_LOC_SOURCES = frozenset({"body", "query", "path", "header", "cookie"})

# A body of a few megabytes can fail validation millions of times; the `400` body and
# the log record carry only the first errors, and names are cut to a sane length.
_MAX_FIELD_ERRORS = 20
_MAX_NAME_LEN = 200

UNMATCHED_PATH = "<unmatched>"

_GENERIC_MESSAGE = "Некорректное значение"
_BAD_BODY_MESSAGE = "Тело запроса отсутствует или имеет неверный формат"
_INVALID_JSON_MESSAGE = "Тело запроса — некорректный JSON"

# User-facing text per Pydantic error `type`; `{…}` is filled from the error's `ctx`.
# Source: https://docs.pydantic.dev/latest/errors/validation_errors/
_MESSAGES: Mapping[str, str] = {
    "missing": "Обязательное поле",
    "extra_forbidden": "Неизвестное поле",
    "string_type": "Ожидается строка",
    "string_too_short": "Не короче {min_length} символов",
    "string_too_long": "Не длиннее {max_length} символов",
    "string_pattern_mismatch": "Значение не соответствует формату",
    "int_type": "Ожидается целое число",
    "int_parsing": "Ожидается целое число",
    "int_from_float": "Ожидается целое число",
    "float_type": "Ожидается число",
    "float_parsing": "Ожидается число",
    "bool_type": "Ожидается true или false",
    "bool_parsing": "Ожидается true или false",
    "greater_than": "Должно быть больше {gt}",
    "greater_than_equal": "Не меньше {ge}",
    "less_than": "Должно быть меньше {lt}",
    "less_than_equal": "Не больше {le}",
    "too_short": "Не меньше {min_length} элементов",
    "too_long": "Не больше {max_length} элементов",
    "enum": "Недопустимое значение",
    "literal_error": "Недопустимое значение",
    "date_type": "Ожидается дата в формате ГГГГ-ММ-ДД",
    "date_parsing": "Ожидается дата в формате ГГГГ-ММ-ДД",
    "date_from_datetime_parsing": "Ожидается дата в формате ГГГГ-ММ-ДД",
    "datetime_type": "Ожидается дата и время в формате ГГГГ-ММ-ДДTЧЧ:ММ:СС",
    "datetime_parsing": "Ожидается дата и время в формате ГГГГ-ММ-ДДTЧЧ:ММ:СС",
    "datetime_from_date_parsing": "Ожидается дата и время в формате ГГГГ-ММ-ДДTЧЧ:ММ:СС",
    "uuid_type": "Ожидается UUID",
    "uuid_parsing": "Ожидается UUID",
    "list_type": "Ожидается список",
    "dict_type": "Ожидается объект",
    "model_type": "Ожидается объект",
    "model_attributes_type": "Ожидается объект",
}


def _field_name(loc: tuple[str | int, ...]) -> str:
    """`("body", "engineers", 2, "skills")` → `engineers[2].skills`; `""` for the body itself."""
    parts = list(loc[1:] if loc and loc[0] in _LOC_SOURCES else loc)
    name = ""
    for part in parts:
        if isinstance(part, int):
            name += f"[{part}]"
        else:
            name += f".{part}" if name else part
    return name[:_MAX_NAME_LEN]


def _message(error: ErrorDetails) -> str:
    template = _MESSAGES.get(error["type"])
    if template is None:
        return _GENERIC_MESSAGE
    try:
        return template.format(**error.get("ctx", {}))
    except KeyError:
        return _GENERIC_MESSAGE


def _validation_error_body(errors: Sequence[ErrorDetails]) -> ValidationError:
    """The `400` body for Pydantic errors: `fields` per parameter, or `message`
    when an error cannot be tied to one (malformed JSON, a body of the wrong shape)."""
    fields: list[FieldError] = []
    for error in errors[:_MAX_FIELD_ERRORS]:
        if error["type"] == "json_invalid":
            return ValidationError(RequestMessage(message=_INVALID_JSON_MESSAGE))
        name = _field_name(error["loc"])
        if not name:
            return ValidationError(RequestMessage(message=_BAD_BODY_MESSAGE))
        fields.append(FieldError(name=name, message=_message(error)))
    if not fields:
        return ValidationError(RequestMessage(message=_BAD_BODY_MESSAGE))
    return ValidationError(FieldErrors(fields=fields))


def _bad_request(body: ValidationError) -> Response:
    return Response(content=body.model_dump_json(), status_code=400, media_type="application/json")


def route_path(request: Request) -> str:
    """The route's path template (e.g. `/tickets/{id}`), never the resolved URL —
    keeps path-parameter values and arbitrary client input out of logs. A request
    no route matched (unknown path, a body rejected before routing) gets a marker."""
    route = request.scope.get("route")
    return route.path if route is not None else UNMATCHED_PATH


async def _unhandled_error_handler(request: Request, exc: Exception) -> Response:
    logger.error(
        "unhandled_error",
        method=request.method,
        path=route_path(request),
        exc_info=exc,
    )
    # Also reached from outside the request middleware, which then never adds
    # the header; the request id is still bound in the logging context.
    request_id = structlog.contextvars.get_contextvars().get("request_id")
    headers = {REQUEST_ID_HEADER: request_id} if request_id else None
    return Response(status_code=500, headers=headers)


async def _app_error_handler(request: Request, exc: Exception) -> Response:
    # Business errors are already logged by the route that raised them.
    if isinstance(exc, InvalidInput):
        if exc.message is not None:
            return _bad_request(ValidationError(RequestMessage(message=exc.message)))
        return _bad_request(
            ValidationError(
                FieldErrors(fields=[FieldError(name=n, message=m) for n, m in exc.fields or ()])
            )
        )
    for error_class, status in _STATUS_BY_ERROR:
        if isinstance(exc, error_class):
            return Response(status_code=status)
    return await _unhandled_error_handler(request, exc)


async def _request_validation_handler(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, RequestValidationError)
    # FastAPI types them as `Sequence[Any]`; they are Pydantic's error dicts.
    errors = cast(Sequence[ErrorDetails], exc.errors())
    first = errors[:_MAX_FIELD_ERRORS]
    # Names only: the rejected values may carry personal data. A malformed-JSON
    # error has a byte offset in `loc`, not a name.
    names = {_field_name(e["loc"]) for e in first if e["type"] != "json_invalid"}
    logger.warning(
        "request_validation_failed",
        path=route_path(request),
        fields=sorted(names - {""}),
        errors_total=len(errors),
    )
    return _bad_request(_validation_error_body(first))


async def _http_exception_handler(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, StarletteHTTPException)
    # FastAPI and Starlette raise `400` themselves on a body they cannot parse
    # (undecodable JSON, a broken multipart form); `400` always carries a body.
    if exc.status_code == 400:
        return _bad_request(ValidationError(RequestMessage(message=_BAD_BODY_MESSAGE)))
    # Same status, without Starlette's `{"detail": ...}` body; headers such as
    # `Allow` on 405 are kept.
    return Response(status_code=exc.status_code, headers=exc.headers)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(RequestValidationError, _request_validation_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    # Starlette runs the `Exception` handler in ServerErrorMiddleware, outside
    # every user middleware.
    # Source: https://www.starlette.io/exceptions/#errors-and-handled-exceptions
    app.add_exception_handler(Exception, _unhandled_error_handler)
