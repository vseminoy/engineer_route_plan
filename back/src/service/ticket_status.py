"""Ticket status changes the dispatcher records from a brigade's reports."""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from psycopg import AsyncConnection

from src.domain import Ticket, TicketStatus
from src.errors import InvalidInput, NotFound
from src.logging import get_logger
from src.repository.db import database_errors
from src.service.loader import Connect

logger = get_logger(__name__)

S = TicketStatus

# The statuses a ticket may move to from each status. Forward along
# not_sent → sent → en_route → in_progress → completed, skipping steps too: the
# dispatcher records what the brigade reported, and the reports in between may be
# missing. completed and cancelled are closed: a closed ticket is final and takes no part
# in later replanning.
NEXT_STATUSES: Mapping[TicketStatus, frozenset[TicketStatus]] = {
    S.NOT_SENT: frozenset({S.SENT, S.EN_ROUTE, S.IN_PROGRESS, S.COMPLETED, S.CANCELLED, S.OVERDUE}),
    S.SENT: frozenset({S.EN_ROUTE, S.IN_PROGRESS, S.COMPLETED, S.CANCELLED, S.OVERDUE}),
    S.EN_ROUTE: frozenset({S.IN_PROGRESS, S.COMPLETED, S.CANCELLED, S.OVERDUE}),
    S.IN_PROGRESS: frozenset({S.COMPLETED, S.CANCELLED}),
    S.OVERDUE: frozenset({S.EN_ROUTE, S.IN_PROGRESS, S.COMPLETED, S.CANCELLED}),
    S.COMPLETED: frozenset(),
    S.CANCELLED: frozenset(),
}

# Statuses in which the brigade has already set out: a cancellation from them wastes the
# trip, and plan metrics count it.
DISPATCHED = frozenset({S.EN_ROUTE, S.IN_PROGRESS})

# Status names as the dispatcher knows them, for the error text shown to the user.
LABELS: Mapping[TicketStatus, str] = {
    S.NOT_SENT: "Не отправлена",
    S.SENT: "Отправлена",
    S.EN_ROUTE: "В пути",
    S.IN_PROGRESS: "В работе",
    S.COMPLETED: "Выполнена",
    S.CANCELLED: "Отменена",
    S.OVERDUE: "Просрочена",
}

LockTicket = Callable[[AsyncConnection[Any], int], Awaitable[Ticket | None]]
UpdateTicketStatus = Callable[[AsyncConnection[Any], int, TicketStatus, bool], Awaitable[Ticket]]


@dataclass(frozen=True)
class TicketStatuses:
    connect: Connect
    lock_ticket: LockTicket
    update_ticket_status: UpdateTicketStatus

    async def change(self, ticket_id: int, status: TicketStatus) -> Ticket:
        """Moves the ticket to `status` if the transition is allowed. The check and the
        write run in one transaction under the ticket's row lock, so concurrent changes of
        one ticket are checked one after another. The ticket's current status is a
        success with nothing written. Plans already built are not touched."""
        async with (
            database_errors("change_ticket_status"),
            self.connect() as conn,
            conn.transaction(),
        ):
            ticket = await self.lock_ticket(conn, ticket_id)
            if ticket is None:
                raise NotFound(reason="ticket_not_found", params={"ticket_id": ticket_id})
            if ticket.status == status:
                return ticket
            if status not in NEXT_STATUSES[ticket.status]:
                raise InvalidInput(
                    reason="transition_not_allowed",
                    message=(
                        f"Статус заявки нельзя изменить с «{LABELS[ticket.status]}»"
                        f" на «{LABELS[status]}»"
                    ),
                    params={
                        "ticket_id": ticket_id,
                        "status_from": ticket.status.value,
                        "status_to": status.value,
                    },
                )
            changed = await self.update_ticket_status(
                conn,
                ticket_id,
                status,
                status == S.CANCELLED and ticket.status in DISPATCHED,
            )
        logger.info(
            "ticket_status_changed",
            ticket_id=ticket_id,
            status_from=ticket.status.value,
            status_to=status.value,
        )
        return changed
