from datetime import time
from pathlib import Path

import pytest

from src.errors import InvalidInput
from src.service.regions import Regions

BACK_DIR = Path(__file__).resolve().parents[2]

CONFIG = """
[regions.east]
name = "Восток"
center = [55.7, 37.7]
engineers = 13

[shifts.morning]
start = "10:00"
end = "18:00"
share = 0.25

[shifts.evening]
start = "15:30"
end = "23:30"
share = 0.25

[shifts.full_day]
start = "10:00"
end = "23:30"

[remote_towns]
"Кашира" = [54.83, 38.15]
"""


def _load(tmp_path: Path, text: str) -> Regions:
    path = tmp_path / "regions.toml"
    path.write_text(text, encoding="utf-8")
    return Regions.from_file(path)


def test_regions_config_shipped() -> None:
    regions = Regions.from_file(BACK_DIR / "data" / "regions.toml")
    assert {code: (r.name, r.engineers) for code, r in regions.regions.items()} == {
        "east": ("Восток", 13),
        "south_east": ("Юго-Восток", 12),
        "south_center": ("Югоцентр", 11),
    }
    shifts = regions.shifts
    assert (shifts.morning.start, shifts.morning.end) == (time(10, 0), time(18, 0))
    assert (shifts.evening.start, shifts.evening.end) == (time(15, 30), time(23, 30))
    assert (shifts.full_day.start, shifts.full_day.end) == (time(10, 0), time(23, 30))
    assert set(regions.remote_towns) == {"Домодедово", "Кашира", "Ступино"}


def test_unknown_region_code(tmp_path: Path) -> None:
    with pytest.raises(InvalidInput) as e:
        _load(tmp_path, CONFIG).get("north")
    assert e.value.reason == "unknown_region"
    assert e.value.fields == [("region", "Неизвестный регион")]


@pytest.mark.parametrize(("start", "end"), [("22:00", "06:00"), ("15:30", "15:30")])
def test_overnight_shift_rejected(tmp_path: Path, start: str, end: str) -> None:
    text = CONFIG.replace('start = "15:30"\nend = "23:30"', f'start = "{start}"\nend = "{end}"')
    with pytest.raises(ValueError, match="midnight"):
        _load(tmp_path, text)


def test_too_many_engineers_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="30"):
        _load(tmp_path, CONFIG.replace("engineers = 13", "engineers = 31"))
    assert _load(tmp_path, CONFIG.replace("engineers = 13", "engineers = 30")) is not None


def test_too_few_full_day_engineers_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="full-day"):
        _load(tmp_path, CONFIG.replace("engineers = 13", "engineers = 5"))
