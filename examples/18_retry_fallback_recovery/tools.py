"""Tool implementations for Pattern 18: Retry Fallback Recovery.

Tools:
- get_account_data: Retrieves account from the mocked unreliable service
- classify_scenario: Single model call to classify error type
- check_circuit_state: Returns current circuit breaker state
- record_dead_letter: Appends a failed request to the dead letter list
"""

from __future__ import annotations

from typing import Any

from adk_patterns.models import ScriptedModel
from adk_patterns.shared import CircuitBreaker, RunContext

from contracts import (
    DeadLetterRecord,
    PermanentError,
    ScenarioClassification,
    TransientError,
)
from fixtures import FIXTURES, MODEL_FIXTURES
from mocks import FallbackCache, MockAccountService


def classify_scenario(
    ctx: RunContext,
    model: ScriptedModel,
    scenario_key: str,
) -> ScenarioClassification:
    """Classify the scenario using a single model call.

    The ScriptedModel returns a deterministic fixture response,
    mapping the scenario key to an error type and configuration.

    Args:
        ctx: Run context for audit tracking.
        model: ScriptedModel with registered fixtures.
        scenario_key: Key identifying the test scenario.

    Returns:
        ScenarioClassification with error type and configuration.
    """
    ctx.audit("classifier", "model_call", resource=scenario_key)

    response = model.invoke(
        system_instruction=(
            "Classify the retrieval scenario into a configured response. "
            "Return the error type, account ID, and retry configuration."
        ),
        messages=[
            {
                "role": "user",
                "content": f"__FIXTURE__:{scenario_key} Scenario: {scenario_key}",
            }
        ],
    )

    ctx.record_model_call(tokens=response.usage.total_tokens)
    ctx.audit("classifier", "model_response", outcome="success")

    if response.structured_output:
        return ScenarioClassification(**response.structured_output)

    # Fallback: direct fixture lookup
    result = FIXTURES.get(scenario_key)
    if result is None:
        ctx.mark_failed(f"No fixture for scenario: {scenario_key}")
        raise ValueError(f"No fixture for scenario: {scenario_key}")

    return result


def get_account_data(
    service: MockAccountService,
    account_id: str,
) -> dict[str, Any]:
    """Retrieve account data from the mocked service.

    May raise TransientError or PermanentError based on
    the service's configured response sequence.

    Args:
        service: The mocked account service.
        account_id: Account identifier to look up.

    Returns:
        Account data dict.
    """
    return service.get_account(account_id)


def check_circuit_state(circuit: CircuitBreaker) -> str:
    """Return the current circuit breaker state.

    Args:
        circuit: The CircuitBreaker instance.

    Returns:
        "closed", "open", or "half-open".
    """
    if circuit.is_open:
        return "open"
    return "closed"


def record_dead_letter(
    dead_letter: list[dict[str, Any]],
    account_id: str,
    error: Exception,
    attempts: int,
) -> list[dict[str, Any]]:
    """Record a failed request into the dead letter list.

    Args:
        dead_letter: The current dead letter list (mutated in place).
        account_id: The account that failed.
        error: The exception that caused the failure.
        attempts: Number of attempts made.

    Returns:
        The updated dead letter list.
    """
    error_type = "transient" if isinstance(error, TransientError) else "permanent"
    if isinstance(error, PermanentError):
        error_type = "permanent"

    record = DeadLetterRecord(
        account_id=account_id,
        error_type=error_type,
        attempts=attempts,
        last_error=str(error),
    )
    dead_letter.append(record.model_dump())
    return dead_letter


# -- Tool definitions for the registry ---------------------------------------

TOOL_REGISTRY: dict[str, Any] = {
    "classify_scenario": classify_scenario,
    "get_account_data": get_account_data,
    "check_circuit_state": check_circuit_state,
    "record_dead_letter": record_dead_letter,
}
