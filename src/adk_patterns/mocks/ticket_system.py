"""Mock ticket system for support workflow patterns."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


@dataclass
class Ticket:
    ticket_id: str
    title: str
    description: str
    status: TicketStatus = TicketStatus.OPEN
    assignee: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class MockTicketSystem:
    """Mock ticket system for testing support workflows."""

    def __init__(self) -> None:
        self._tickets: dict[str, Ticket] = {}

    def create(self, ticket: Ticket) -> Ticket:
        self._tickets[ticket.ticket_id] = ticket
        return ticket

    def get(self, ticket_id: str) -> Ticket | None:
        return self._tickets.get(ticket_id)

    def update_status(self, ticket_id: str, status: TicketStatus) -> Ticket:
        ticket = self._tickets.get(ticket_id)
        if not ticket:
            raise ValueError(f"Ticket {ticket_id} not found")
        ticket.status = status
        return ticket

    def assign(self, ticket_id: str, assignee: str) -> Ticket:
        ticket = self._tickets.get(ticket_id)
        if not ticket:
            raise ValueError(f"Ticket {ticket_id} not found")
        ticket.assignee = assignee
        return ticket

    def reset(self) -> None:
        self._tickets.clear()
