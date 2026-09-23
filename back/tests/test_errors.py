from typing import Any

import pytest

from src.errors import AppError, Conflict, DependencyUnavailable, InvalidInput, NotFound


def test_domain_errors_share_app_error_base() -> None:
    for cls in (InvalidInput, NotFound, Conflict, DependencyUnavailable):
        assert issubclass(cls, AppError)


def test_app_error_carries_reason_and_params() -> None:
    e = NotFound(reason="plan_not_found", params={"plan_id": 7})

    assert e.reason == "plan_not_found"
    assert e.params == {"plan_id": 7}


def test_app_error_params_default_to_empty() -> None:
    assert Conflict(reason="x").params == {}


def test_invalid_input_with_message() -> None:
    e = InvalidInput(reason="file_empty", message="Файл не содержит ни одной заявки")

    assert e.message == "Файл не содержит ни одной заявки"
    assert e.fields is None


def test_invalid_input_with_fields() -> None:
    e = InvalidInput(
        reason="window_order", fields=[("window_start", "Начало окна позже его окончания")]
    )

    assert e.fields == [("window_start", "Начало окна позже его окончания")]
    assert e.message is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"message": "m", "fields": [("a", "b")]},
        {"fields": []},
    ],
    ids=["neither", "both", "empty_fields"],
)
def test_invalid_input_requires_exactly_one_of_message_fields(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        InvalidInput(reason="x", **kwargs)


def test_domain_error_subclass_keeps_base_mapping() -> None:
    class PlanNotFound(NotFound):
        pass

    assert isinstance(PlanNotFound(reason="plan_not_found"), NotFound)
