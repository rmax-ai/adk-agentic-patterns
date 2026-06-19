"""Mocked account service and fallback cache for Pattern 18.

Provides:
- MockAccountService: configurable unreliable service with transient/permanent errors
- FallbackCache: simple stale-data cache for fallback scenarios
"""

from __future__ import annotations

from typing import Any

from contracts import AccountData, PermanentError, TransientError


class FallbackCache:
    """Simple cache that returns stale data when the service is unavailable."""

    def __init__(self) -> None:
        self._cache: dict[str, dict[str, Any]] = {}

    def get(self, account_id: str) -> dict[str, Any] | None:
        """Return cached data for account_id, or None."""
        return self._cache.get(account_id)

    def set(self, account_id: str, data: dict[str, Any]) -> None:
        """Store data in cache."""
        self._cache[account_id] = dict(data)

    def prime(self, account_id: str, data: dict[str, Any]) -> None:
        """Pre-populate cache with stale data for fallback tests."""
        self._cache[account_id] = dict(data)

    def clear(self) -> None:
        """Clear all cached data."""
        self._cache.clear()


class MockAccountService:
    """Mocked unreliable account data service.

    Configure with set_responses() or use convenience methods
    for common test scenarios.
    """

    def __init__(self) -> None:
        self._call_count: int = 0
        self._responses: list[tuple[Exception | None, dict[str, Any] | None]] = []
        self._default_account_data: dict[str, Any] = {
            "account_id": "ACC-001",
            "name": "Alice Smith",
            "balance": 2500.00,
        }

    # -- Convenience configuration methods ----------------------------------

    def set_success_mode(self, account_data: dict[str, Any] | None = None) -> None:
        """All calls succeed immediately."""
        data = account_data or self._default_account_data
        self._responses = [(None, dict(data))]

    def set_transient_then_success_mode(
        self,
        num_transient: int = 2,
        account_data: dict[str, Any] | None = None,
    ) -> None:
        """N transient errors, then success."""
        data = account_data or self._default_account_data
        responses: list[tuple[Exception | None, dict[str, Any] | None]] = [
            (TransientError("Service temporarily unavailable"), None)
        ] * num_transient
        responses.append((None, dict(data)))
        self._responses = responses

    def set_permanent_error_mode(self) -> None:
        """Always fails with permanent error."""
        self._responses = [
            (PermanentError("Account not found: invalid account ID"), None)
        ]

    def set_always_transient_mode(self) -> None:
        """Always fails with transient error (never recovers)."""
        self._responses = [
            (TransientError("Service temporarily unavailable"), None)
        ]

    def set_responses(
        self, responses: list[tuple[Exception | None, dict[str, Any] | None]]
    ) -> None:
        """Configure exact sequence of (error, result) pairs."""
        self._responses = list(responses)

    # -- Core retrieval method ----------------------------------------------

    def get_account(self, account_id: str) -> dict[str, Any]:
        """Retrieve account data.

        Raises TransientError or PermanentError based on configuration.
        """
        if not self._responses:
            self.set_success_mode()

        idx = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        error, result = self._responses[idx]

        if error is not None:
            raise error

        if result is not None:
            result["account_id"] = account_id  # keep requested ID
            return dict(result)

        return {"account_id": account_id, "name": "Unknown", "balance": 0.0}

    @property
    def call_count(self) -> int:
        return self._call_count

    def reset(self) -> None:
        """Reset call counter and clear configured responses."""
        self._call_count = 0
        self._responses.clear()
