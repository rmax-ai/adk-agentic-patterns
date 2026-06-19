"""Mocks for Pattern 12: Shared Workspace / Blackboard.

Provides a mock clock and helper utilities for testing optimistic locking
and concurrent access scenarios.
"""

from __future__ import annotations


class MockClock:
    """A simple mock clock for deterministic time in tests."""

    def __init__(self, start_time: float = 0.0) -> None:
        self._time = start_time

    def now(self) -> float:
        return self._time

    def tick(self, delta: float = 1.0) -> None:
        self._time += delta

    def reset(self, start_time: float = 0.0) -> None:
        self._time = start_time
