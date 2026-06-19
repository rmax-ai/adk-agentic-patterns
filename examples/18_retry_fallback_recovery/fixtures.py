"""Fixture definitions for Pattern 18: Retry Fallback Recovery.

Pre-configured ScriptedModel fixtures that classify scenarios
into the correct error type and configuration.
"""

from __future__ import annotations

from adk_patterns.models import structured_response

from contracts import ScenarioClassification

# -- Fixtures for the single model call ---------------------------------------

FIXTURES: dict[str, ScenarioClassification] = {
    "success": ScenarioClassification(
        error_type="success",
        reason="No errors expected — service is healthy",
        account_id="ACC-001",
        max_retries=3,
        fallback_available=True,
    ),
    "transient_then_success": ScenarioClassification(
        error_type="transient",
        reason="Transient errors expected — service will recover after retries",
        account_id="ACC-001",
        max_retries=3,
        fallback_available=True,
    ),
    "permanent_error": ScenarioClassification(
        error_type="permanent",
        reason="Permanent error — account not found, do not retry",
        account_id="ACC-999",
        max_retries=3,
        fallback_available=False,
    ),
    "circuit_breaker": ScenarioClassification(
        error_type="transient",
        reason="Multiple transient errors to trigger circuit breaker opening",
        account_id="ACC-001",
        max_retries=3,
        fallback_available=True,
    ),
    "fallback_cache": ScenarioClassification(
        error_type="transient",
        reason="Circuit will open, fallback cache should return stale data",
        account_id="ACC-001",
        max_retries=3,
        fallback_available=True,
    ),
    "dead_letter": ScenarioClassification(
        error_type="transient",
        reason="All retries will exhaust, recording into dead letter",
        account_id="ACC-001",
        max_retries=3,
        fallback_available=False,
    ),
    "retry_exhaustion": ScenarioClassification(
        error_type="transient",
        reason="Persistent transient errors exhausting all retry attempts",
        account_id="ACC-001",
        max_retries=3,
        fallback_available=False,
    ),
    "exponential_backoff": ScenarioClassification(
        error_type="transient",
        reason="Verifying backoff delays increase with each attempt",
        account_id="ACC-001",
        max_retries=3,
        fallback_available=False,
    ),
}

# -- Build model fixture dict for registration -------------------------------

MODEL_FIXTURES = {
    key: structured_response(value.model_dump())
    for key, value in FIXTURES.items()
}
