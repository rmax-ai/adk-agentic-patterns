"""Mock email service for notification patterns."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Email:
    to: str
    subject: str
    body: str
    metadata: dict[str, Any] = field(default_factory=dict)


class MockEmailService:
    """Mock email service — records sent emails for test verification."""

    def __init__(self) -> None:
        self._sent: list[Email] = []

    def send(self, email: Email) -> None:
        self._sent.append(email)

    @property
    def sent(self) -> list[Email]:
        return list(self._sent)

    @property
    def sent_count(self) -> int:
        return len(self._sent)

    def reset(self) -> None:
        self._sent.clear()
