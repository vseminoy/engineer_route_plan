from datetime import date, datetime, time

import pytest

from src.clients.osrm import TravelMatrix
from src.domain import Engineer, Point, Skill, Ticket, TicketStatus, VehicleType
from src.service.explain import (
    ExplainedPlan,
    UnassignedReason,
    explain,
)
from src.service.solver import DayPlan, EngineerRoute, SolveStatus, Visit
from tests.log_records import events, json_logs, records

DAY = date(2026, 9, 1)
POINT = Point(lat=55.75, lon=37.6)
CAR, FOOT, BIKE = VehicleType.CAR, VehicleType.FOOT, VehicleType.BIKE
LOCAL, CONNECTION, EMERGENCY = Skill.LOCAL_WORK, Skill.CONNECTION, Skill.EMERGENCY


def at(hh: int, mm: int = 0) -> datetime:
    return datetime.combine(DAY, time(hh, mm))


def engineer(
    id: int,
    skills: tuple[Skill, ...] = (LOCAL,),
    vehicle: VehicleType = CAR,
    shift: tuple[time, time] = (time(10, 0), time(23, 30)),
) -> Engineer:
    return Engineer(
        id=id,
        name=f"Бригада {id}",
        start=POINT,
        shift_start=shift[0],
        shift_end=shift[1],
        vehicle_type=vehicle,
        skills=skills,
    )


def ticket(
    id: int,
    skill: Skill = LOCAL,
    window: tuple[datetime, datetime] = (at(10), at(22)),
    duration: int = 30,
    vehicle: VehicleType | None = None,
) -> Ticket:
    return Ticket(
        id=id,
        external_id=f"T{id}",
        type_bk=None,
        type_hd="Тест",
        required_skill=skill,
        required_vehicle=vehicle,
        priority=3,
        district=None,
        address="адрес",
        location=POINT,
        window_start=window[0],
        window_end=window[1],
        duration_min=duration,
        status=TicketStatus.SENT,
        received_at=at(0),
    )


def line(positions: list[float]) -> dict:
    return {
        v: TravelMatrix(
            durations_s=[[abs(a - b) * 60 for b in positions] for a in positions],
            distances_m=[[abs(a - b) * 1000 for b in positions] for a in positions],
        )
        for v in VehicleType
    }


def unassigned_plan(ticket_ids: list[int], engineers: list[Engineer]) -> DayPlan:
    return DayPlan(
        status=SolveStatus.FEASIBLE,
        routes=tuple(EngineerRoute(e.id, (), idle_min=0) for e in engineers),
        unassigned=tuple(ticket_ids),
    )


# --- Проходит без изменений ---


def test_infeasible_passthrough(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    plan = DayPlan(status=SolveStatus.INFEASIBLE, routes=(), unassigned=())
    result = explain(plan, [], [], line([0]), day=DAY)
    assert result == ExplainedPlan(status=SolveStatus.INFEASIBLE, routes=(), unassigned=())
    assert records(capsys) == []


# --- Назначенные заявки: текст ---


def test_assigned_explanation_fields() -> None:
    e = engineer(1, (CONNECTION,))
    t = ticket(1, CONNECTION, window=(at(10), at(14)))
    visit = Visit(
        ticket_id=1,
        arrival=at(10, 18),
        start=at(10, 18),
        end=at(10, 48),
        travel_min=18,
        distance_m=1000,
    )
    plan = DayPlan(
        status=SolveStatus.OPTIMAL, routes=(EngineerRoute(1, (visit,), idle_min=0),), unassigned=()
    )
    result = explain(plan, [t], [e], line([0, 1]), day=DAY)
    text = result.routes[0].visits[0].explanation
    assert "Бригада 1" in text
    assert "Подключение" in text
    assert "10:00" in text and "14:00" in text
    assert "автомобиле" in text
    assert "18 мин" in text
    for jargon in ("penalty", "dimension", "allowed vehicles", "штраф"):
        assert jargon not in text


def test_assigned_explanation_uses_own_window_not_computed_start() -> None:
    e = engineer(1)
    t = ticket(1, window=(at(10), at(14)))
    visit = Visit(
        ticket_id=1, arrival=at(10), start=at(10, 30), end=at(11), travel_min=0, distance_m=0
    )
    plan = DayPlan(
        status=SolveStatus.OPTIMAL, routes=(EngineerRoute(1, (visit,), idle_min=0),), unassigned=()
    )
    text = explain(plan, [t], [e], line([0, 0]), day=DAY).routes[0].visits[0].explanation
    assert "10:00" in text and "14:00" in text
    assert "10:30" not in text


# --- Атрибуция причины: пять групп ограничений по порядку ---


def test_no_skill() -> None:
    engineers = [engineer(1, (LOCAL, CONNECTION))]
    t = ticket(1, EMERGENCY)
    plan = unassigned_plan([1], engineers)
    result = explain(plan, [t], engineers, line([0, 1]), day=DAY)
    assert result.unassigned[0].reason == UnassignedReason.NO_SKILL


def test_no_vehicle() -> None:
    engineers = [engineer(1, (LOCAL,), CAR), engineer(2, (LOCAL,), FOOT)]
    t = ticket(1, vehicle=BIKE)
    plan = unassigned_plan([1], engineers)
    result = explain(plan, [t], engineers, line([0, 0, 1]), day=DAY)
    assert result.unassigned[0].reason == UnassignedReason.NO_VEHICLE


def test_no_time_slot() -> None:
    engineers = [engineer(1, shift=(time(10), time(20)))]
    t = ticket(1, window=(at(10), at(10, 15)))
    plan = unassigned_plan([1], engineers)
    result = explain(plan, [t], engineers, line([0, 30]), day=DAY)
    assert result.unassigned[0].reason == UnassignedReason.NO_TIME_SLOT


def test_shift_overflow() -> None:
    engineers = [engineer(1, shift=(time(10), time(11)))]
    t = ticket(1, window=(at(10), at(10, 30)), duration=70)
    plan = unassigned_plan([1], engineers)
    result = explain(plan, [t], engineers, line([0, 5]), day=DAY)
    assert result.unassigned[0].reason == UnassignedReason.SHIFT_OVERFLOW


def test_no_time_slot_before_shift_overflow() -> None:
    engineers = [
        engineer(1, shift=(time(10), time(20))),  # window unreachable for this one (too far)
        engineer(2, shift=(time(10), time(10, 30))),  # window reachable, shift too short
    ]
    t = ticket(1, window=(at(10), at(10, 10)), duration=30)
    # positions: engineer 1 far (95 min travel, misses the window), engineer 2 close (5 min).
    plan = unassigned_plan([1], engineers)
    result = explain(plan, [t], engineers, line([100, 0, 5]), day=DAY)
    assert result.unassigned[0].reason == UnassignedReason.SHIFT_OVERFLOW


def test_all_eligible_engineers_booked_elsewhere() -> None:
    engineers = [engineer(1, shift=(time(10), time(20)))]
    t = ticket(1, window=(at(10), at(20)), duration=30)
    plan = unassigned_plan([1], engineers)
    result = explain(plan, [t], engineers, line([0, 5]), day=DAY)
    assert result.unassigned[0].reason == UnassignedReason.ALL_ELIGIBLE_ENGINEERS_BOOKED_ELSEWHERE


def test_attribution_ignores_actual_route() -> None:
    """The brigade is technically eligible on skill/vehicle/window/shift alone, whatever it is
    doing in the plan's own routes — attribution never reads `plan.routes`."""
    engineers = [engineer(1, shift=(time(10), time(20)))]
    t = ticket(1, window=(at(10), at(20)), duration=30)
    busy_elsewhere = Visit(
        ticket_id=99, arrival=at(10), start=at(10), end=at(19, 59), travel_min=0, distance_m=0
    )
    plan = DayPlan(
        status=SolveStatus.FEASIBLE,
        routes=(EngineerRoute(1, (busy_elsewhere,), idle_min=0),),
        unassigned=(1,),
    )
    result = explain(
        plan, [t, ticket(99, window=(at(10), at(20)))], engineers, line([0, 5, 5]), day=DAY
    )
    assert result.unassigned[0].reason == UnassignedReason.ALL_ELIGIBLE_ENGINEERS_BOOKED_ELSEWHERE


def test_no_route_excludes_candidate() -> None:
    engineers = [engineer(1, shift=(time(10), time(20)))]
    t = ticket(1, window=(at(10), at(20)))
    matrices = line([0, 5])
    matrices[CAR].durations_s[0][1] = None
    matrices[CAR].distances_m[0][1] = None
    plan = unassigned_plan([1], engineers)
    result = explain(plan, [t], engineers, matrices, day=DAY)
    assert result.unassigned[0].reason == UnassignedReason.NO_TIME_SLOT


# --- Неназначенные заявки: текст ---


@pytest.mark.parametrize(
    ("setup", "reason"),
    [
        (
            lambda: ([engineer(1, (LOCAL,))], ticket(1, EMERGENCY), line([0, 1])),
            UnassignedReason.NO_SKILL,
        ),
        (
            lambda: ([engineer(1, (LOCAL,), CAR)], ticket(1, vehicle=BIKE), line([0, 1])),
            UnassignedReason.NO_VEHICLE,
        ),
        (
            lambda: (
                [engineer(1, shift=(time(10), time(20)))],
                ticket(1, window=(at(10), at(10, 15))),
                line([0, 30]),
            ),
            UnassignedReason.NO_TIME_SLOT,
        ),
        (
            lambda: (
                [engineer(1, shift=(time(10), time(11)))],
                ticket(1, window=(at(10), at(10, 30)), duration=70),
                line([0, 5]),
            ),
            UnassignedReason.SHIFT_OVERFLOW,
        ),
        (
            lambda: (
                [engineer(1, shift=(time(10), time(20)))],
                ticket(1, window=(at(10), at(20)), duration=30),
                line([0, 5]),
            ),
            UnassignedReason.ALL_ELIGIBLE_ENGINEERS_BOOKED_ELSEWHERE,
        ),
    ],
    ids=["no_skill", "no_vehicle", "no_time_slot", "shift_overflow", "all_booked"],
)
def test_unassigned_explanation_fields(setup: object, reason: UnassignedReason) -> None:
    from src.service.explain import _SKILL_RU

    engineers, t, matrices = setup()  # type: ignore[operator]
    plan = unassigned_plan([1], engineers)
    result = explain(plan, [t], engineers, matrices, day=DAY)
    row = result.unassigned[0]
    assert row.reason == reason
    text = row.explanation
    assert _SKILL_RU[t.required_skill] in text  # the required skill, every reason names it
    if reason not in (UnassignedReason.NO_SKILL, UnassignedReason.NO_VEHICLE):
        assert "10:00" in text  # the window, once it is the actual reason under discussion
    if t.required_vehicle:
        assert "велосипед" in text
    if reason == UnassignedReason.ALL_ELIGIBLE_ENGINEERS_BOOKED_ELSEWHERE:
        assert "1" in text  # one technically eligible brigade
    for jargon in ("penalty", "dimension", "allowed vehicles", "штраф"):
        assert jargon not in text


# --- Согласованность входа ---


def test_matrix_size_mismatch_rejected() -> None:
    engineers = [engineer(1)]
    t = ticket(1)
    plan = unassigned_plan([1], engineers)
    with pytest.raises(ValueError, match="travel matrix size"):
        explain(plan, [t], engineers, line([0, 1, 2]), day=DAY)


def test_missing_matrix_for_vehicle_rejected() -> None:
    engineers = [engineer(1, vehicle=BIKE)]
    t = ticket(1)
    plan = unassigned_plan([1], engineers)
    matrices = line([0, 1])
    del matrices[BIKE]
    with pytest.raises(ValueError, match="no travel matrix"):
        explain(plan, [t], engineers, matrices, day=DAY)


# --- Логи ---


def test_unassigned_reason_attributed_logged(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs("DEBUG")
    engineers = [engineer(1, (LOCAL,))]
    t1 = ticket(1, EMERGENCY)
    t2 = ticket(2, window=(at(10), at(10, 5)))
    plan = unassigned_plan([1, 2], engineers)
    explain(plan, [t1, t2], engineers, line([0, 1, 30]), day=DAY)
    found = events(capsys, "unassigned_reason_attributed")
    assert len(found) == 2
    assert {r["ticket_id"] for r in found} == {1, 2}
    assert all(r["level"] == "debug" for r in found)
    assert {r["reason_code"] for r in found} == {"no_skill", "no_time_slot"}


def test_unassigned_reasons_summary_logged(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    engineers = [engineer(1, (LOCAL,))]
    tickets = [ticket(1, EMERGENCY), ticket(2, EMERGENCY), ticket(3, window=(at(10), at(10, 1)))]
    plan = unassigned_plan([1, 2, 3], engineers)
    explain(plan, tickets, engineers, line([0, 1, 1, 30]), day=DAY)
    (record,) = events(capsys, "unassigned_reasons_summary")
    assert record["level"] == "info"
    assert record["no_skill"] == 2
    assert record["no_time_slot"] == 1


def test_logs_no_ticket_data_beyond_id(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs("DEBUG")
    e = engineer(1, (CONNECTION,))
    assigned = ticket(90001, CONNECTION, window=(at(10), at(14)))
    visit = Visit(
        ticket_id=90001, arrival=at(10), start=at(10), end=at(10, 30), travel_min=0, distance_m=0
    )
    unassigned_ticket = ticket(90002, EMERGENCY)
    plan = DayPlan(
        status=SolveStatus.OPTIMAL,
        routes=(EngineerRoute(1, (visit,), idle_min=0),),
        unassigned=(90002,),
    )
    explain(plan, [assigned, unassigned_ticket], [e], line([0, 1, 1]), day=DAY)
    found = records(capsys)
    assert found
    text = repr(found)
    for secret in ("адрес", str(POINT.lat), str(POINT.lon)):
        assert secret not in text
