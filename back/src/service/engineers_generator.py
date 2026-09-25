"""Demo brigades of a region: the input files carry tickets only."""

import random

from src.domain import EngineerDraft, Point, Skill, VehicleType
from src.service.regions import Region, Regions

_SKILLS = tuple(Skill)
_VEHICLES = tuple(VehicleType)


def generate_engineers(
    region: Region, regions: Regions, office: Point, districts: set[str]
) -> list[EngineerDraft]:
    """Deterministic for the same input: the random source is seeded by the region code.

    Full-day brigades come first and between them hold every skill and every vehicle
    type, so every skill and every vehicle type is on duty all day whatever shifts the
    others got (not every pair of them). Each brigade has 1 to 3 skills. For each
    remote town among the ticket districts one full-day brigade starts at the town's
    point; the rest start at the office.
    """
    rng = random.Random(region.code)
    shifts = regions.shifts
    morning, evening, full_day = shifts.split(region.engineers)
    kinds = [shifts.full_day] * full_day + [shifts.morning] * morning + [shifts.evening] * evening
    towns = [regions.remote_towns[t] for t in sorted(districts & regions.remote_towns.keys())]

    engineers = []
    for i, shift in enumerate(kinds):
        base = _SKILLS[i % len(_SKILLS)]
        extra = rng.sample([s for s in _SKILLS if s != base], rng.randint(0, 2))
        skills = tuple(s for s in _SKILLS if s == base or s in extra)
        start = towns[i] if i < min(len(towns), full_day) else office
        engineers.append(
            EngineerDraft(
                name=f"Бригада {i + 1}",
                start=start,
                shift_start=shift.start,
                shift_end=shift.end,
                vehicle_type=_VEHICLES[i % len(_VEHICLES)],
                skills=skills,
            )
        )
    return engineers
