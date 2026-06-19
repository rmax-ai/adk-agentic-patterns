"""Mock event log — append-only event store for audit and durability patterns."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LogEntry:
    """A single entry in the event log."""

    entry_id: str
    event_type: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0


class EventLog:
    """Append-only event log. Used by durable SAGA and audit patterns."""

    def __init__(self) -> None:
        self._entries: list[LogEntry] = []

    def append(self, entry: LogEntry) -> None:
        self._entries.append(entry)

    def get_all(self) -> list[LogEntry]:
        return list(self._entries)

    def get_by_type(self, event_type: str) -> list[LogEntry]:
        return [e for e in self._entries if e.event_type == event_type]

    def count(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()
