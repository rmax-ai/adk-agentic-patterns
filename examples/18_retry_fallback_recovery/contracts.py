"""Contracts and error taxonomy for Pattern 18: Retry Fallback Recovery.

Defines:
- Account data model (the payload being retrieved)
- TransientError / PermanentError taxonomy
- DeadLetterRecord for failed requests
- Scenario classification schema
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AccountData(BaseModel):
    """Account data returned by the mocked service."""

    account_id: str = Field(description="Account identifier")
    name: str = Field(description="Account holder name")
    balance: float = Field(description="Current account balance")


class DeadLetterRecord(BaseModel):
    """Record of a failed request that could not be recovered."""

    account_id: str = Field(description="Account identifier that failed")
    error_type: str = Field(description="transient or permanent")
    attempts: int = Field(description="Number of retry attempts made")
    last_error: str = Field(description="Last error message")


# -- Error taxonomy -----------------------------------------------------------

class TransientError(Exception):
    """A transient error that can be retried (e.g., timeout, rate limit)."""

    def __init__(self, message: str = "Service temporarily unavailable"):
        self.message = message
        super().__init__(message)


class PermanentError(Exception):
    """A permanent error that must not be retried (e.g., not found, auth)."""

    def __init__(self, message: str = "Permanent error"):
        self.message = message
        super().__init__(message)


# -- Scenario classification --------------------------------------------------

class ScenarioClassification(BaseModel):
    """Output of the single model call — classifies the scenario."""

    error_type: str = Field(description="success, transient, or permanent")
    reason: str = Field(description="Brief reason for the classification")
    account_id: str = Field(default="ACC-001", description="Account ID to look up")
    max_retries: int = Field(default=3, description="Maximum retry attempts")
    fallback_available: bool = Field(default=True, description="Whether fallback cache is primed")


# -- Retry state model --------------------------------------------------------

class RetryState(BaseModel):
    """Snapshot of the retry state machine at any point."""

    account_data: AccountData | None = None
    retry_count: int = 0
    circuit_state: str = "closed"  # closed, open, half-open
    dead_letter: list[dict[str, Any]] = Field(default_factory=list)
