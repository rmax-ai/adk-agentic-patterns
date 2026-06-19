"""Pattern 18: Retry Fallback Recovery.

Scenario: Retrieve account data from an unreliable mocked service.

Demonstrates:
- Transient vs permanent error taxonomy
- Bounded exponential backoff with deterministic jitter
- Circuit breaker (open after 3 failures, reset after timeout)
- Fallback cache (stale data when service unavailable)
- Dead-letter record for failed requests
- Single model call for error classification only — retries use no LLM

State keys: account_data, retry_count, circuit_state, dead_letter[]
Budget:    max_model_calls=1, max_tool_calls=10
"""

from __future__ import annotations

import time
from typing import Any

from adk_patterns.config import Config
from adk_patterns.contracts import PatternRunResult
from adk_patterns.models import ScriptedModel
from adk_patterns.shared import (
    CircuitBreaker,
    RetryConfig,
    RunContext,
    compute_backoff,
    run_scope,
)

from contracts import (
    AccountData,
    PermanentError,
    RetryState,
    TransientError,
)
from fixtures import MODEL_FIXTURES
from mocks import FallbackCache, MockAccountService
from tools import (
    check_circuit_state,
    classify_scenario,
    get_account_data,
    record_dead_letter,
)

# -- Default configuration ----------------------------------------------------

DEFAULT_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    base_delay_ms=100.0,
    max_delay_ms=5000.0,
    backoff_multiplier=2.0,
    jitter_ms=0.0,
    retry_on=(TransientError,),
)

CIRCUIT_BREAKER_CONFIG = {
    "failure_threshold": 3,
    "reset_timeout_ms": 5000.0,
}


# -- Core orchestration -------------------------------------------------------


def run_retry_loop(
    ctx: RunContext,
    service: MockAccountService,
    circuit: CircuitBreaker,
    cache: FallbackCache,
    account_id: str,
    retry_cfg: RetryConfig,
    classification: Any,
) -> RetryState:
    """Deterministic retry loop with circuit breaker and fallback cache.

    No model calls are made in this loop — retry logic is purely
    procedural Python.

    Args:
        ctx: Run context for audit and budget tracking.
        service: The mocked account service.
        circuit: Circuit breaker for failure protection.
        cache: Fallback cache for stale data.
        account_id: Account to look up.
        retry_cfg: Retry configuration.
        classification: Scenario classification from the model call.

    Returns:
        RetryState with final account_data, retry_count,
        circuit_state, and dead_letter records.
    """
    state = RetryState()
    dead_letter: list[dict[str, Any]] = []
    fallback_available = getattr(classification, "fallback_available", True)

    for attempt in range(1, retry_cfg.max_attempts + 1):
        ctx.record_iteration()

        # Check circuit breaker state
        if circuit.is_open:
            state.circuit_state = "open"
            ctx.audit(
                "retry_orchestrator",
                "circuit_open",
                resource=account_id,
                outcome="fallback",
                metadata={"attempt": attempt},
            )

            # Try fallback cache
            if fallback_available:
                cached = cache.get(account_id)
                if cached is not None:
                    state.account_data = AccountData(**cached)
                    state.retry_count = attempt - 1
                    ctx.audit(
                        "retry_orchestrator",
                        "fallback_cache_hit",
                        resource=account_id,
                        outcome="success",
                        metadata={"cached": cached},
                    )
                    ctx.snapshot_state(state.model_dump())
                    return state

            # No fallback available — record dead letter
            ctx.audit(
                "retry_orchestrator",
                "fallback_cache_miss",
                resource=account_id,
                outcome="failure",
                metadata={"attempt": attempt},
            )
            dead_letter = record_dead_letter(
                dead_letter, account_id,
                TransientError("Circuit breaker open, no fallback"),
                attempt,
            )
            state.dead_letter = dead_letter
            ctx.snapshot_state(state.model_dump())
            return state

        # Attempt to fetch account data
        try:
            data = get_account_data(service, account_id)
            circuit.record_success()
            state.circuit_state = "closed"
            state.account_data = AccountData(**data)
            state.retry_count = attempt - 1

            # Update cache with fresh data
            cache.set(account_id, data)

            ctx.audit(
                "retry_orchestrator",
                "account_retrieved",
                resource=account_id,
                outcome="success",
                metadata={"attempt": attempt},
            )
            ctx.snapshot_state(state.model_dump())
            return state

        except TransientError as e:
            circuit.record_failure()
            state.retry_count = attempt
            state.circuit_state = "closed" if not circuit.is_open else "open"

            ctx.audit(
                "retry_orchestrator",
                "transient_error",
                resource=account_id,
                outcome="failure",
                metadata={
                    "attempt": attempt,
                    "error": str(e),
                    "circuit_state": state.circuit_state,
                },
            )

            if attempt < retry_cfg.max_attempts and not circuit.is_open:
                # Compute backoff delay and wait
                delay_ms = compute_backoff(attempt, retry_cfg)
                ctx.audit(
                    "retry_orchestrator",
                    "backoff_wait",
                    resource=account_id,
                    outcome="retrying",
                    metadata={
                        "attempt": attempt,
                        "delay_ms": delay_ms,
                        "backoff_base": retry_cfg.base_delay_ms,
                    },
                )
                time.sleep(delay_ms / 1000.0)
            else:
                # Retries exhausted or circuit opened — record dead letter
                dead_letter = record_dead_letter(
                    dead_letter, account_id, e, attempt,
                )
                state.dead_letter = dead_letter
                ctx.audit(
                    "retry_orchestrator",
                    "dead_letter_recorded",
                    resource=account_id,
                    outcome="failure",
                    metadata={
                        "attempt": attempt,
                        "error": str(e),
                        "max_attempts": retry_cfg.max_attempts,
                    },
                )
                if circuit.is_open and fallback_available:
                    cached = cache.get(account_id)
                    if cached is not None:
                        state.account_data = AccountData(**cached)
                        ctx.audit(
                            "retry_orchestrator",
                            "fallback_cache_hit",
                            resource=account_id,
                            outcome="success",
                            metadata={"cached": cached},
                        )
                break

        except PermanentError as e:
            dead_letter = record_dead_letter(dead_letter, account_id, e, attempt)
            state.dead_letter = dead_letter
            state.retry_count = attempt
            ctx.audit(
                "retry_orchestrator",
                "permanent_error",
                resource=account_id,
                outcome="failure",
                metadata={
                    "attempt": attempt,
                    "error": str(e),
                },
            )
            break

        except Exception as e:
            # Unexpected error — treat as transient and retry
            circuit.record_failure()
            state.retry_count = attempt

            ctx.audit(
                "retry_orchestrator",
                "unexpected_error",
                resource=account_id,
                outcome="failure",
                metadata={
                    "attempt": attempt,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )

            if attempt < retry_cfg.max_attempts:
                delay_ms = compute_backoff(attempt, retry_cfg)
                time.sleep(delay_ms / 1000.0)
            else:
                dead_letter = record_dead_letter(
                    dead_letter, account_id, e, attempt,
                )
                state.dead_letter = dead_letter
                break

    ctx.snapshot_state(state.model_dump())
    return state


def run(
    config: Config | None = None,
    scenario: str = "default",
    retry_config: RetryConfig | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    cache: FallbackCache | None = None,
    service: MockAccountService | None = None,
) -> PatternRunResult:
    """Entry point for CLI and tests.

    Args:
        config: Application configuration (uses defaults if None).
        scenario: Test scenario key.
        retry_config: Retry configuration (defaults if None).
        circuit_breaker: CircuitBreaker instance (created if None).
        cache: FallbackCache instance (created if None).
        service: MockAccountService instance (created if None).

    Returns:
        A PatternRunResult with status, output, metrics, and audit trail.
    """
    # Resolve defaults
    retry_cfg = retry_config or DEFAULT_RETRY_CONFIG
    circuit = circuit_breaker or CircuitBreaker(**CIRCUIT_BREAKER_CONFIG)
    fallback_cache = cache or FallbackCache()
    mock_service = service or MockAccountService()

    # Pre-populate fallback cache with stale data for fallback tests
    stale_data = {
        "account_id": "ACC-001",
        "name": "Alice Smith (stale)",
        "balance": 2400.00,
    }
    fallback_cache.prime("ACC-001", stale_data)

    # Set up ScriptedModel with registered fixtures
    model = ScriptedModel()
    model.register_fixtures(MODEL_FIXTURES)

    with run_scope(
        "retry-fallback-recovery",
        scenario,
        max_model_calls=1,
        max_tool_calls=10,
        max_iterations=10,
    ) as ctx:
        # Step 1: Single model call to classify the scenario (no LLM for retries)
        classification = classify_scenario(ctx, model, scenario)
        ctx.audit(
            "orchestrator",
            "scenario_classified",
            resource=scenario,
            metadata={
                "error_type": classification.error_type,
                "account_id": classification.account_id,
                "max_retries": classification.max_retries,
            },
        )

        # Adjust retry config based on scenario
        scenario_retry_cfg = RetryConfig(
            max_attempts=classification.max_retries,
            base_delay_ms=retry_cfg.base_delay_ms,
            max_delay_ms=retry_cfg.max_delay_ms,
            backoff_multiplier=retry_cfg.backoff_multiplier,
            jitter_ms=retry_cfg.jitter_ms,
            retry_on=retry_cfg.retry_on,
        )

        # Configure the mock service based on the scenario
        _configure_mock_service(mock_service, scenario)

        # Step 2: Deterministic retry loop (no model calls)
        state = run_retry_loop(
            ctx,
            mock_service,
            circuit,
            fallback_cache,
            classification.account_id,
            scenario_retry_cfg,
            classification,
        )

        ctx.output = state.model_dump()
        ctx.snapshot_state(state.model_dump())

        # Determine final status
        if state.account_data is not None:
            ctx.status = ctx.status  # keep SUCCEEDED (default)
        elif state.dead_letter:
            ctx.status = ctx.status  # keep SUCCEEDED (pattern completed)
            ctx.audit(
                "orchestrator",
                "run_completed_with_dead_letter",
                outcome="partial",
                metadata={"dead_letter_count": len(state.dead_letter)},
            )
        else:
            ctx.mark_failed("No account data retrieved")

    return ctx.to_result()


# -- Mock service configuration -----------------------------------------------


def _configure_mock_service(service: MockAccountService, scenario: str) -> None:
    """Configure the mock service based on the scenario key.

    Maps scenario names to service behavior configurations.
    """
    config_map = {
        "default": "success",
        "success": "success",
        "transient_then_success": "transient_then_success",
        "permanent_error": "permanent_error",
        "circuit_breaker": "always_transient",
        "fallback_cache": "always_transient",
        "dead_letter": "always_transient",
        "retry_exhaustion": "always_transient",
        "exponential_backoff": "always_transient",
    }

    mode = config_map.get(scenario, "success")

    if mode == "success":
        service.set_success_mode()
    elif mode == "transient_then_success":
        service.set_transient_then_success_mode(num_transient=2)
    elif mode == "permanent_error":
        service.set_permanent_error_mode()
    elif mode == "always_transient":
        service.set_always_transient_mode()


# -- Entry point for CLI ------------------------------------------------------


def main(
    config: Config | None = None,
    scenario: str = "default",
) -> PatternRunResult:
    """Standard entry point called by CLI."""
    return run(config=config, scenario=scenario)
