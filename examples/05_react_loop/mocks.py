"""Mock data service for Pattern 05: ReAct Loop.

Provides simulated metrics, log entries, and deployment history
for the incident diagnosis scenario."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MockIncidentData:
    """Simulated incident data for a fictional service outage."""

    metrics: dict[str, dict[str, float]] = field(default_factory=lambda: {
        "api-gateway": {
            "cpu_usage": 89.5,
            "memory_usage": 76.2,
            "error_rate": 12.3,
            "latency_p99": 2450.0,
            "request_rate": 1520.0,
        },
        "user-service": {
            "cpu_usage": 45.1,
            "memory_usage": 52.0,
            "error_rate": 0.5,
            "latency_p99": 120.0,
            "request_rate": 890.0,
        },
        "payment-service": {
            "cpu_usage": 34.2,
            "memory_usage": 41.8,
            "error_rate": 0.1,
            "latency_p99": 95.0,
            "request_rate": 340.0,
        },
    })

    logs: dict[str, list[dict]] = field(default_factory=lambda: {
        "api-gateway": [
            {"level": "ERROR", "message": "Upstream connection timeout to user-service", "count": 142},
            {"level": "WARN", "message": "Rate limit approaching threshold (85%)", "count": 23},
            {"level": "ERROR", "message": "502 Bad Gateway from user-service/user/profile", "count": 67},
            {"level": "INFO", "message": "Circuit breaker opened for user-service", "count": 1},
        ],
        "user-service": [
            {"level": "INFO", "message": "Service operating normally", "count": 500},
            {"level": "WARN", "message": "Database connection pool at 60% capacity", "count": 3},
        ],
        "payment-service": [
            {"level": "INFO", "message": "Service operating normally", "count": 200},
        ],
    })

    deployments: dict[str, list[dict]] = field(default_factory=lambda: {
        "api-gateway": [
            {
                "version": "v2.4.1",
                "timestamp": "2026-06-19T02:00:00Z",
                "changes": ["Updated rate limiting config", "Added new endpoint /v2/checkout"],
            },
            {
                "version": "v2.4.0",
                "timestamp": "2026-06-18T12:00:00Z",
                "changes": ["Rewrote connection pool logic", "Bumped dependency: httpx 0.28→0.29"],
            },
        ],
        "user-service": [
            {
                "version": "v1.9.2",
                "timestamp": "2026-06-17T08:00:00Z",
                "changes": ["Database schema migration: added profiles.indexed_lookup"],
            },
        ],
        "payment-service": [
            {
                "version": "v3.1.0",
                "timestamp": "2026-06-15T10:00:00Z",
                "changes": ["Replaced payment processor SDK"],
            },
        ],
    })

    _diagnosis_submitted: bool = False
    _submission_count: int = 0

    def reset(self) -> None:
        """Reset mutable state for test isolation."""
        self._diagnosis_submitted = False
        self._submission_count = 0

    @property
    def diagnosis_submitted(self) -> bool:
        return self._diagnosis_submitted

    def submit_diagnosis(self) -> dict:
        self._diagnosis_submitted = True
        self._submission_count += 1
        return {
            "status": "diagnosis_recorded",
            "submission_id": f"DIAG-{self._submission_count:03d}",
        }


# Singleton shared across tool calls
_shared_data: MockIncidentData | None = None


def get_shared_data() -> MockIncidentData:
    """Get or create the shared mock data instance."""
    global _shared_data
    if _shared_data is None:
        _shared_data = MockIncidentData()
    return _shared_data


def reset_shared_data() -> None:
    """Reset the shared mock data instance (for test isolation)."""
    global _shared_data
    if _shared_data is not None:
        _shared_data.reset()
    else:
        _shared_data = MockIncidentData()
