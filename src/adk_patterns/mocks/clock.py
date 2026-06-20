"""Mock clock for deterministic time in tests.

Avoids time.sleep in tests. All patterns use this for timing control.
"""

from __future__ import annotations


class MockClock:
    """Deterministic clock for testing.

    Time only advances when explicitly ticked. Use in all pattern tests
    instead of time.sleep or asyncio.sleep.
    """

    def __init__(self, start_time: float = 0.0) -> None:
        self._now = start_time

    def tick(self, seconds: float = 0.1) -> float:
        """Advance the clock by the given seconds."""
        self._now += seconds
        return self._now

    def now(self) -> float:
        return self._now

    def monotonic(self) -> float:
        return self._now

    def time(self) -> float:
        return self._now
