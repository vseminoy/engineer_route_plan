from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import psycopg
import pytest
from psycopg_pool import PoolTimeout

from src.domain import Point, Skill, Ticket, TicketStatus
from src.errors import DatabaseFailure, DependencyUnavailable, InvalidInput, NotFound
from src.service.ticket_status import TicketStatuses
from tests.log_records import events, json_logs

S = TicketStatus

# The transition table of the operation, written out in full rather than derived: the
# tests hold the service to the approved table, not to the rule it was built from.
ALLOWED = {
    S.NOT_SENT: {S.SENT, S.EN_ROUTE, S.IN_PROGRESS, S.COMPLETED, S.CANCELLED, S.OVERDUE},
    S.SENT: {S.EN_ROUTE, S.IN_PROGRESS, S.COMPLETED, S.CANCELLED, S.OVERDUE},
    S.EN_ROUTE: {S.IN_PROGRESS, S.COMPLETED, S.CANCELLED, S.OVERDUE},
    S.IN_PROGRESS: {S.COMPLETED, S.CANCELLED},
    S.OVERDUE: {S.EN_ROUTE, S.IN_PROGRESS, S.COMPLETED, S.CANCELLED},
    S.COMPLETED: set(),
    S.CANCELLED: set(),
}


def _ticket(status: TicketStatus, ticket_id: int = 87) -> Ticket:
    return Ticket(
        id=ticket_id,
        external_id="1",
        type_bk=None,
        type_hd="Авария",
        required_skill=Skill.EMERGENCY,
        required_vehicle=None,
        priority=1,
        district=None,
        address="Город Москва, ул.Тестовая, д. 1",
        location=Point(lat=55.72, lon=37.74),
        window_start=datetime(2026, 8, 17, 10, 0),
        window_end=datetime(2026, 8, 17, 12, 0),
        duration_min=80,
        status=status,
        received_at=datetime(2026, 8, 17, 0, 0),
    )


class FakeConnection:
    """Records how its one transaction ended; fails the commit with `commit_error`."""

    def __init__(self, commit_error: Exception | None = None) -> None:
        self.outcome: str | None = None
        self.commit_error = commit_error

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        try:
            yield
        except BaseException:
            self.outcome = "rollback"
            raise
        if self.commit_error:
            self.outcome = "rollback"
            raise self.commit_error
        self.outcome = "commit"


class FakeConnect:
    """Stands in for the pool's `connection`, or fails to give one with `error`."""

    def __init__(
        self, error: Exception | None = None, commit_error: Exception | None = None
    ) -> None:
        self.error = error
        self.conn = FakeConnection(commit_error)

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[Any]:
        if self.error:
            raise self.error
        yield self.conn


class FakeRepository:
    def __init__(
        self,
        status: TicketStatus | None,
        lock_error: Exception | None = None,
        update_error: Exception | None = None,
    ) -> None:
        self.status = status
        self.lock_error = lock_error
        self.update_error = update_error
        self.updates: list[tuple[int, TicketStatus, bool]] = []

    async def lock_ticket(self, _conn: Any, ticket_id: int) -> Ticket | None:
        if self.lock_error:
            raise self.lock_error
        return None if self.status is None else _ticket(self.status, ticket_id)

    async def update_ticket_status(
        self, _conn: Any, ticket_id: int, status: TicketStatus, cancelled_after_dispatch: bool
    ) -> Ticket:
        self.updates.append((ticket_id, status, cancelled_after_dispatch))
        if self.update_error:
            raise self.update_error
        return _ticket(status, ticket_id)


def _service(repo: FakeRepository, connect: FakeConnect | None = None) -> TicketStatuses:
    return TicketStatuses(connect or FakeConnect(), repo.lock_ticket, repo.update_ticket_status)


@pytest.mark.parametrize(
    ("status_from", "status_to"), [(a, b) for a in TicketStatus for b in TicketStatus]
)
async def test_transition_table(status_from: TicketStatus, status_to: TicketStatus) -> None:
    repo = FakeRepository(status_from)
    connect = FakeConnect()
    service = _service(repo, connect)
    if status_to == status_from:
        ticket = await service.change(87, status_to)
        assert ticket.status is status_from
        assert repo.updates == []
    elif status_to in ALLOWED[status_from]:
        ticket = await service.change(87, status_to)
        assert ticket.status is status_to
        assert [(i, s) for i, s, _ in repo.updates] == [(87, status_to)]
        assert connect.conn.outcome == "commit"
    else:
        with pytest.raises(InvalidInput) as e:
            await service.change(87, status_to)
        assert e.value.reason == "transition_not_allowed"
        assert repo.updates == []


async def test_transition_not_allowed() -> None:
    repo = FakeRepository(S.COMPLETED)
    connect = FakeConnect()
    with pytest.raises(InvalidInput) as e:
        await _service(repo, connect).change(87, S.EN_ROUTE)
    assert e.value.reason == "transition_not_allowed"
    assert e.value.message == "Статус заявки нельзя изменить с «Выполнена» на «В пути»"
    assert e.value.params == {"ticket_id": 87, "status_from": "completed", "status_to": "en_route"}
    assert repo.updates == []
    assert connect.conn.outcome == "rollback"


@pytest.mark.parametrize(
    ("status_from", "status_to"),
    [(a, b) for a in (S.COMPLETED, S.CANCELLED) for b in TicketStatus if b != a],
)
async def test_closed_ticket_stays_closed(
    status_from: TicketStatus, status_to: TicketStatus
) -> None:
    repo = FakeRepository(status_from)
    with pytest.raises(InvalidInput) as e:
        await _service(repo).change(87, status_to)
    assert e.value.reason == "transition_not_allowed"
    assert repo.updates == []


@pytest.mark.parametrize(
    ("status_from", "status_to"),
    [(S.SENT, S.NOT_SENT), (S.IN_PROGRESS, S.EN_ROUTE), (S.IN_PROGRESS, S.OVERDUE)],
)
async def test_back_along_chain_not_allowed(
    status_from: TicketStatus, status_to: TicketStatus
) -> None:
    with pytest.raises(InvalidInput) as e:
        await _service(FakeRepository(status_from)).change(87, status_to)
    assert e.value.reason == "transition_not_allowed"


async def test_forward_skip_allowed() -> None:
    repo = FakeRepository(S.SENT)
    ticket = await _service(repo).change(87, S.COMPLETED)
    assert ticket.status is S.COMPLETED
    assert repo.updates == [(87, S.COMPLETED, False)]


@pytest.mark.parametrize(
    ("status_from", "flag"),
    [
        (S.EN_ROUTE, True),
        (S.IN_PROGRESS, True),
        (S.NOT_SENT, False),
        (S.SENT, False),
        (S.OVERDUE, False),
    ],
)
async def test_cancelled_after_dispatch(status_from: TicketStatus, flag: bool) -> None:
    repo = FakeRepository(status_from)
    await _service(repo).change(87, S.CANCELLED)
    assert repo.updates == [(87, S.CANCELLED, flag)]


async def test_not_cancel_keeps_flag_false() -> None:
    repo = FakeRepository(S.IN_PROGRESS)
    await _service(repo).change(87, S.COMPLETED)
    assert repo.updates == [(87, S.COMPLETED, False)]


async def test_status_change_logged(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    connect = FakeConnect()
    await _service(FakeRepository(S.SENT), connect).change(87, S.EN_ROUTE)
    (record,) = events(capsys, "ticket_status_changed")
    assert record["level"] == "info"
    assert (record["ticket_id"], record["status_from"], record["status_to"]) == (
        87,
        "sent",
        "en_route",
    )
    assert "address" not in record
    assert connect.conn.outcome == "commit"


async def test_same_status_not_logged(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    await _service(FakeRepository(S.EN_ROUTE)).change(87, S.EN_ROUTE)
    assert events(capsys, "ticket_status_changed") == []


async def test_ticket_not_found() -> None:
    repo = FakeRepository(None)
    with pytest.raises(NotFound) as e:
        await _service(repo).change(87, S.COMPLETED)
    assert e.value.reason == "ticket_not_found"
    assert e.value.params == {"ticket_id": 87}
    assert repo.updates == []


@pytest.mark.parametrize("where", ["lock", "update"])
@pytest.mark.parametrize(
    "error",
    [DependencyUnavailable(reason="db_unavailable"), DatabaseFailure(reason="db_query_failed")],
)
async def test_repository_failure_propagates(
    where: str, error: Exception, capsys: pytest.CaptureFixture[str]
) -> None:
    json_logs()
    repo = FakeRepository(
        S.SENT,
        lock_error=error if where == "lock" else None,
        update_error=error if where == "update" else None,
    )
    connect = FakeConnect()
    with pytest.raises(type(error)) as e:
        await _service(repo, connect).change(87, S.EN_ROUTE)
    assert e.value is error
    assert connect.conn.outcome == "rollback"
    assert events(capsys, "ticket_status_changed") == []


async def test_pool_timeout_is_dependency_unavailable(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    repo = FakeRepository(S.SENT)
    with pytest.raises(DependencyUnavailable) as e:
        await _service(repo, FakeConnect(PoolTimeout("no connection"))).change(87, S.EN_ROUTE)
    assert e.value.reason == "db_unavailable"
    assert repo.updates == []
    (record,) = events(capsys, "db_query_failed")
    assert record["query"] == "change_ticket_status"


async def test_commit_failure_is_dependency_unavailable(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    repo = FakeRepository(S.SENT)
    connect = FakeConnect(commit_error=psycopg.OperationalError("server closed the connection"))
    with pytest.raises(DependencyUnavailable) as e:
        await _service(repo, connect).change(87, S.EN_ROUTE)
    assert e.value.reason == "db_unavailable"
    assert repo.updates == [(87, S.EN_ROUTE, False)]
    (record,) = events(capsys, "db_query_failed")
    assert record["query"] == "change_ticket_status"
    assert events(capsys, "ticket_status_changed") == []
