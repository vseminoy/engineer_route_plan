import pytest
from pydantic import ValidationError

from src.api.schemas.generated.common import LocalDateTime, LocalTime


def test_local_datetime_accepts_local_time() -> None:
    assert LocalDateTime.model_validate("2026-09-23T13:20:00").root == "2026-09-23T13:20:00"


@pytest.mark.parametrize("value", ["2026-09-23T13:20:00Z", "2026-09-23T13:20:00+03:00"])
def test_local_datetime_rejects_zone(value: str) -> None:
    with pytest.raises(ValidationError):
        LocalDateTime.model_validate(value)


@pytest.mark.parametrize(
    "value", ["2026-09-23T13:20:00.5", "2026-09-23 13:20:00", "2026-09-23T13:20", ""]
)
def test_local_datetime_rejects_other_forms(value: str) -> None:
    with pytest.raises(ValidationError):
        LocalDateTime.model_validate(value)


@pytest.mark.parametrize(
    "value",
    ["2026-13-01T10:00:00", "2026-09-32T10:00:00", "2026-09-23T24:00:00", "2026-09-23T10:60:00"],
)
def test_local_datetime_rejects_out_of_range(value: str) -> None:
    with pytest.raises(ValidationError):
        LocalDateTime.model_validate(value)


@pytest.mark.parametrize("value", ["00:00", "13:20", "23:59"])
def test_local_time_accepts_hours_minutes(value: str) -> None:
    assert LocalTime.model_validate(value).root == value


@pytest.mark.parametrize("value", ["13:20:00", "9:05", "24:00", "12:60", "13:20+03:00", ""])
def test_local_time_rejects_other_forms(value: str) -> None:
    with pytest.raises(ValidationError):
        LocalTime.model_validate(value)
