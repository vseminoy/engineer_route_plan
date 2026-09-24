"""Domain errors, independent of HTTP.

`reason` is a stable snake_case code for logs; `params` holds the business
parameters of the failed operation. Personal data does not belong in either.
"""

from collections.abc import Mapping, Sequence


class AppError(Exception):
    def __init__(self, reason: str, params: Mapping[str, object] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.params: dict[str, object] = dict(params or {})


class InvalidInput(AppError):
    """Input rejected by a business check the contract cannot express.

    Carries exactly one of `message` (the request as a whole) or `fields`
    (`(parameter name as in the contract, text)` pairs). Both texts are shown
    to the user as is.
    """

    def __init__(
        self,
        reason: str,
        *,
        message: str | None = None,
        fields: Sequence[tuple[str, str]] | None = None,
        params: Mapping[str, object] | None = None,
    ) -> None:
        if (message is None) == (not fields):
            raise ValueError("InvalidInput needs exactly one of message or non-empty fields")
        super().__init__(reason, params)
        self.message = message
        self.fields = list(fields) if fields else None


class NotFound(AppError):
    pass


class Conflict(AppError):
    pass


class DependencyUnavailable(AppError):
    """The database or an external service failed; the request may be retried."""


class DatabaseFailure(AppError):
    """The database rejected a query in a way a retry would not fix (a constraint,
    malformed data, an error in the SQL). The driver's details are logged where the
    error happened and never reach the response."""
