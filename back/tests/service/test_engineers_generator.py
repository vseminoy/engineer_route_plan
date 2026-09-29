from collections import Counter
from datetime import time
from pathlib import Path

import pytest

from src.domain import EngineerDraft, Point, Skill, VehicleType
from src.service.engineers_generator import generate_engineers
from src.service.regions import Regions

BACK_DIR = Path(__file__).resolve().parents[2]
OFFICE = Point(lat=55.7, lon=37.7)
REGIONS = Regions.from_file(BACK_DIR / "data" / "regions.toml")
CODES = sorted(REGIONS.regions)
FULL_DAY = (time(10, 0), time(23, 30))


def _generate(
    code: str,
    districts: set[str] | None = None,
    engineers: int | None = None,
    morning_share: float | None = None,
    evening_share: float | None = None,
    seed: str | None = None,
) -> list[EngineerDraft]:
    """Defaults to the region's own config parameters — the same input the demo set is
    generated with in `loader.py`."""
    region = REGIONS.regions[code]
    assert REGIONS.shifts.morning.share is not None
    assert REGIONS.shifts.evening.share is not None
    return generate_engineers(
        REGIONS,
        engineers if engineers is not None else region.engineers,
        morning_share if morning_share is not None else REGIONS.shifts.morning.share,
        evening_share if evening_share is not None else REGIONS.shifts.evening.share,
        seed if seed is not None else code,
        OFFICE,
        districts or {"Выхино"},
    )


def test_count_from_param() -> None:
    assert len(_generate("east", engineers=13)) == 13


@pytest.mark.parametrize("code", CODES)
def test_skills_one_to_three(code: str) -> None:
    for e in _generate(code):
        assert 1 <= len(e.skills) <= 3
        assert len(set(e.skills)) == len(e.skills)


@pytest.mark.parametrize("code", CODES)
def test_all_skills_and_vehicles_present(code: str) -> None:
    engineers = _generate(code)
    assert {s for e in engineers for s in e.skills} == set(Skill)
    assert {e.vehicle_type for e in engineers} == set(VehicleType)


def test_shift_kinds_split() -> None:
    shifts = Counter((e.shift_start, e.shift_end) for e in _generate("east"))
    assert shifts == {
        (time(10, 0), time(18, 0)): 3,
        (time(15, 30), time(23, 30)): 3,
        FULL_DAY: 7,
    }


def test_shift_kinds_split_custom_shares() -> None:
    """Doles are the set's own parameter, not the region's configuration."""
    shifts = Counter(
        (e.shift_start, e.shift_end)
        for e in _generate("east", engineers=15, morning_share=0.2, evening_share=0.2)
    )
    assert shifts == {
        (time(10, 0), time(18, 0)): 3,
        (time(15, 30), time(23, 30)): 3,
        FULL_DAY: 9,
    }


@pytest.mark.parametrize("code", CODES)
def test_full_day_covers_skills_and_vehicles(code: str) -> None:
    full_day = [e for e in _generate(code) if (e.shift_start, e.shift_end) == FULL_DAY]
    assert {s for e in full_day for s in e.skills} == set(Skill)
    assert {e.vehicle_type for e in full_day} == set(VehicleType)


@pytest.mark.parametrize("code", CODES)
def test_shifts_within_one_day(code: str) -> None:
    for e in _generate(code):
        assert e.shift_start < e.shift_end <= time(23, 59)


def test_deterministic() -> None:
    assert _generate("south_east") == _generate("south_east")


def test_different_seed_different_roster() -> None:
    a = _generate("south_east", seed="south_east")
    b = _generate("south_east", seed="other-seed")
    assert a != b


def test_start_at_office() -> None:
    assert {e.start for e in _generate("east")} == {OFFICE}


def test_remote_town_start() -> None:
    engineers = _generate("south_east", {"Домодедово", "Ступино", "Братеево"})
    towns = {REGIONS.remote_towns["Домодедово"], REGIONS.remote_towns["Ступино"]}
    from_towns = [e for e in engineers if e.start in towns]
    assert {e.start for e in from_towns} == towns
    assert len(from_towns) == 2
    assert all((e.shift_start, e.shift_end) == FULL_DAY for e in from_towns)
    assert all(e.start == OFFICE for e in engineers if e not in from_towns)


@pytest.mark.parametrize("code", CODES)
def test_names_without_personal_data(code: str) -> None:
    names = [e.name for e in _generate(code)]
    assert names == [f"Бригада {i}" for i in range(1, len(names) + 1)]
