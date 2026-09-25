"""Regions and the shifts of their demo brigades."""

import math
import tomllib
from datetime import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.domain import Point
from src.errors import InvalidInput

# Full-day brigades must together hold every vehicle type, and there are four of them.
MIN_FULL_DAY_ENGINEERS = 4


def _point(value: object) -> object:
    if isinstance(value, list | tuple) and len(value) == 2:
        return {"lat": value[0], "lon": value[1]}
    return value


class Shift(BaseModel):
    """Working hours, local time; the shift never crosses midnight."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    start: time
    end: time
    share: float | None = Field(default=None, gt=0, lt=1)

    @model_validator(mode="after")
    def _within_one_day(self) -> "Shift":
        if self.start >= self.end:
            raise ValueError("a shift starts before it ends and does not cross midnight")
        return self


class Shifts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    morning: Shift
    evening: Shift
    full_day: Shift

    @model_validator(mode="after")
    def _shares(self) -> "Shifts":
        if self.morning.share is None or self.evening.share is None:
            raise ValueError("morning and evening shifts need a share")
        if self.full_day.share is not None:
            raise ValueError("the full-day shift takes the brigades left over and has no share")
        return self

    def split(self, engineers: int) -> tuple[int, int, int]:
        """(morning, evening, full day) brigade counts."""
        assert self.morning.share is not None and self.evening.share is not None
        morning = math.floor(engineers * self.morning.share)
        evening = math.floor(engineers * self.evening.share)
        return morning, evening, engineers - morning - evening


class Region(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    name: str
    center: Point
    engineers: int = Field(gt=0)

    @field_validator("center", mode="before")
    @classmethod
    def _center_point(cls, value: object) -> object:
        return _point(value)


class Regions(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    regions: dict[str, Region]
    shifts: Shifts
    remote_towns: dict[str, Point]

    @field_validator("regions", mode="before")
    @classmethod
    def _codes(cls, value: object) -> object:
        if isinstance(value, dict):
            return {code: {"code": code, **body} for code, body in value.items()}
        return value

    @field_validator("remote_towns", mode="before")
    @classmethod
    def _town_points(cls, value: object) -> object:
        if isinstance(value, dict):
            return {town: _point(p) for town, p in value.items()}
        return value

    @model_validator(mode="after")
    def _enough_full_day(self) -> "Regions":
        for region in self.regions.values():
            full_day = self.shifts.split(region.engineers)[2]
            if full_day < MIN_FULL_DAY_ENGINEERS:
                raise ValueError(
                    f"regions.{region.code}: {full_day} full-day brigades, "
                    f"at least {MIN_FULL_DAY_ENGINEERS} needed"
                )
        return self

    @classmethod
    def from_file(cls, path: Path) -> "Regions":
        with path.open("rb") as f:
            return cls.model_validate(tomllib.load(f))

    def get(self, code: str) -> Region:
        region = self.regions.get(code)
        if region is None:
            raise InvalidInput(
                "unknown_region",
                fields=[("region", "Неизвестный регион")],
                params={"region": code[:50]},
            )
        return region
