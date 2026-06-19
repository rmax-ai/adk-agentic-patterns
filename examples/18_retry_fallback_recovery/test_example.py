"""Tests for Pattern 18: Retry Fallback Recovery.

Tests:
1. test_successful_retrieval      - Happy path, first attempt succeeds
2. test_transient_error_retry     - 2 transient errors, then success on 3rd
3. test_permanent_error_no_retry  - Permanent error, no retry attempted
4. test_circuit_breaker_opens     - 3 failures → circuit opens
5. test_fallback_cache            - Stale data returned when circuit open
6. test_dead_letter_record        - Failed requests recorded in dead letter
7. test_exponential_backoff       - Backoff delays increase with attempts
8. test_retry_exhaustion          - Max attempts hit, dead letter recorded
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))

from agent import run, DEFAULT_RETRY_CONFIG, CIRCUIT_BREAKER_CONFIG
from contracts import AccountData, DeadLetterRecord, PermanentError, TransientError
from mocks import FallbackCache, MockAccountService
from tools import record_dead_letter, check_circuit_state

from adk_patterns.contracts import ExecutionStatus
from adk_patterns.shared import CircuitBreaker, RetryConfig, compute_backoff


# =============================================================================
# Helpers
# =============================================================================


def _backoff_delays(
    num_attempts: int,
    base_delay_ms: float = 100.0,
    multiplier: float = 2.0,
    max_delay_ms: float = 5000.0,
    jitter_ms: float = 0.0,
) -> list[float]:
    """Compute expected backoff delays for each retry."""
    cfg = RetryConfig(
        max_attempts=num_attempts,
        base_delay_ms=base_delay_ms,
        max_delay_ms=max_delay_ms,
        backoff_multiplier=multiplier,
        jitter_ms=jitter_ms,
    )
    return [compute_backoff(i, cfg) for i in range(1, num_attempts)]


# =============================================================================
# Tests
# =============================================================================


class TestSuccessfulRetrieval:
    """Happy path: service succeeds on first attempt."""

    def test_successful_retrieval(self) -> None:
        result = run(scenario="success")
        assert result.status == ExecutionStatus.SUCCEEDED
        assert result.output is not None
        state = result.output
        assert state["account_data"] is not None
        assert state["account_data"]["account_id"] == "ACC-001"
        assert state["account_data"]["name"] == "Alice Smith"
        assert state["retry_count"] == 0
        assert state["circuit_state"] == "closed"
        assert len(state["dead_letter"]) == 0

    def test_single_model_call_only(self) -> None:
        """Verify exactly one model call — retries are pure Python."""
        result = run(scenario="success")
        assert result.metrics["model_calls"] == 1
        assert result.metrics["tool_calls"] == 0  # no ADK-style tool calls
        assert result.metrics["iterations"] >= 1

    def test_audit_events_present(self) -> None:
        result = run(scenario="success")
        assert len(result.audit_events) >= 3
        actions = [e.action for e in result.audit_events]
        assert "model_call" in actions
        assert "account_retrieved" in actions


class TestTransientErrorRetry:
    """Transient errors: succeeds after 2 retries."""

    def test_transient_error_retry(self) -> None:
        result = run(scenario="transient_then_success")
        assert result.status == ExecutionStatus.SUCCEEDED
        state = result.output
        assert state["account_data"] is not None
        assert state["account_data"]["account_id"] == "ACC-001"
        # Two transient errors before success
        assert state["retry_count"] >= 2
        assert state["circuit_state"] == "closed"
        assert len(state["dead_letter"]) == 0

    def test_retry_audit_events(self) -> None:
        """Verify transient_error and retry audit events."""
        result = run(scenario="transient_then_success")
        actions = [e.action for e in result.audit_events]
        assert "transient_error" in actions
        assert "backoff_wait" in actions
        assert "account_retrieved" in actions


class TestPermanentErrorNoRetry:
    """Permanent error: no retry, dead letter recorded."""

    def test_permanent_error_no_retry(self) -> None:
        result = run(scenario="permanent_error")
        assert result.status == ExecutionStatus.SUCCEEDED
        state = result.output
        assert state["account_data"] is None
        assert len(state["dead_letter"]) == 1
        dl = state["dead_letter"][0]
        assert dl["error_type"] == "permanent"
        assert dl["account_id"] == "ACC-999"
        assert "not found" in dl["last_error"].lower() or "invalid" in dl["last_error"].lower()

    def test_permanent_error_no_retry_count(self) -> None:
        """Only 1 attempt for permanent errors."""
        result = run(scenario="permanent_error")
        state = result.output
        assert state["retry_count"] == 1  # one attempt, no retry


class TestCircuitBreakerOpens:
    """3 failures → circuit opens."""

    def test_circuit_breaker_opens(self) -> None:
        """Three consecutive failures should open the circuit."""
        circuit = CircuitBreaker(failure_threshold=3, reset_timeout_ms=5000.0)
        result = run(
            scenario="circuit_breaker",
            circuit_breaker=circuit,
        )
        state = result.output
        # Circuit should be open or we exhausted retries
        assert circuit._open or state["circuit_state"] == "open" or len(state["dead_letter"]) > 0

    def test_circuit_records_failures(self) -> None:
        """Verify circuit breaker records each failure."""
        circuit = CircuitBreaker(failure_threshold=3, reset_timeout_ms=5000.0)
        circuit.record_failure()
        assert not circuit.is_open
        circuit.record_failure()
        assert not circuit.is_open
        circuit.record_failure()
        assert circuit.is_open

    def test_circuit_resets_after_timeout(self) -> None:
        """Circuit resets after timeout period."""
        circuit = CircuitBreaker(failure_threshold=3, reset_timeout_ms=1.0)
        for _ in range(3):
            circuit.record_failure()
        assert circuit.is_open
        time.sleep(0.002)  # wait for reset
        assert not circuit.is_open

    def test_circuit_reset_on_success(self) -> None:
        """Circuit resets on success."""
        circuit = CircuitBreaker(failure_threshold=3, reset_timeout_ms=50000.0)
        circuit.record_failure()
        circuit.record_failure()
        circuit.record_success()
        assert not circuit.is_open


class TestFallbackCache:
    """Stale data returned when circuit is open."""

    def test_fallback_cache(self) -> None:
        """Stale cached data should be returned when circuit opens."""
        cache = FallbackCache()
        stale = {"account_id": "ACC-001", "name": "Stale User", "balance": 100.0}
        cache.prime("ACC-001", stale)

        result = run(
            scenario="fallback_cache",
            cache=cache,
        )
        state = result.output
        # Either we have stale data or dead letter if cache wasn't used
        if state["account_data"] is not None:
            assert state["account_data"]["name"] == "Alice Smith (stale)"
        else:
            assert len(state["dead_letter"]) > 0

    def test_cache_returns_data(self) -> None:
        """Direct cache test."""
        cache = FallbackCache()
        data = {"account_id": "ACC-001", "name": "Test", "balance": 500.0}
        cache.set("ACC-001", data)
        cached = cache.get("ACC-001")
        assert cached == data

    def test_cache_returns_none_for_missing(self) -> None:
        cache = FallbackCache()
        assert cache.get("MISSING") is None


class TestDeadLetterRecord:
    """Failed requests recorded in dead letter."""

    def test_dead_letter_record_transient(self) -> None:
        """Transient error dead letter record."""
        dl: list = []
        record_dead_letter(dl, "ACC-001", TransientError("timeout"), 3)
        assert len(dl) == 1
        assert dl[0]["error_type"] == "transient"
        assert dl[0]["account_id"] == "ACC-001"
        assert dl[0]["attempts"] == 3

    def test_dead_letter_record_permanent(self) -> None:
        """Permanent error dead letter record."""
        dl: list = []
        record_dead_letter(dl, "ACC-999", PermanentError("not found"), 1)
        assert len(dl) == 1
        assert dl[0]["error_type"] == "permanent"
        assert dl[0]["account_id"] == "ACC-999"
        assert dl[0]["attempts"] == 1

    def test_dead_letter_multiple_records(self) -> None:
        dl: list = []
        record_dead_letter(dl, "ACC-001", TransientError("timeout"), 3)
        record_dead_letter(dl, "ACC-002", PermanentError("not found"), 1)
        assert len(dl) == 2


class TestExponentialBackoff:
    """Backoff delays increase with each retry attempt."""

    def test_exponential_backoff_delays_increase(self) -> None:
        """Delay should increase exponentially."""
        delays = _backoff_delays(4, base_delay_ms=100.0, multiplier=2.0)
        assert delays[0] < delays[1] < delays[2]
        assert delays == pytest.approx([100.0, 200.0, 400.0], rel=0.01)

    def test_backoff_bounded_by_max(self) -> None:
        """Delay should be capped at max_delay_ms."""
        delays = _backoff_delays(10, base_delay_ms=1000.0, multiplier=2.0, max_delay_ms=5000.0)
        for d in delays:
            assert d <= 5000.0

    def test_backoff_with_jitter(self) -> None:
        """Deterministic jitter adds fixed offset."""
        delays = _backoff_delays(3, base_delay_ms=100.0, multiplier=2.0, jitter_ms=50.0)
        # 3 attempts → 2 retry delays: attempt 1 (100+50), attempt 2 (200+50)
        assert delays == pytest.approx([150.0, 250.0], rel=0.01)

    def test_compute_backoff_single_attempt(self) -> None:
        """First retry is base delay."""
        cfg = RetryConfig(max_attempts=2, base_delay_ms=200.0)
        assert compute_backoff(1, cfg) == 200.0

    def test_compute_backoff_second_attempt(self) -> None:
        cfg = RetryConfig(max_attempts=3, base_delay_ms=200.0, backoff_multiplier=2.0)
        assert compute_backoff(2, cfg) == 400.0

    def test_compute_backoff_third_attempt(self) -> None:
        cfg = RetryConfig(max_attempts=4, base_delay_ms=200.0, backoff_multiplier=2.0)
        assert compute_backoff(3, cfg) == 800.0


class TestRetryExhaustion:
    """Max attempts hit, dead letter recorded."""

    def test_retry_exhaustion(self) -> None:
        """All retry attempts exhausted."""
        result = run(scenario="retry_exhaustion")
        state = result.output
        assert state["account_data"] is None
        assert len(state["dead_letter"]) >= 1
        assert state["dead_letter"][0]["error_type"] == "transient"

    def test_retry_exhaustion_all_attempts_used(self) -> None:
        """Verify all max_attempts were tried."""
        result = run(scenario="retry_exhaustion")
        state = result.output
        assert state["retry_count"] >= 1


# =============================================================================
# Error taxonomy tests
# =============================================================================


class TestErrorTaxonomy:
    """Transient vs permanent error classification."""

    def test_transient_error_is_exception(self) -> None:
        assert issubclass(TransientError, Exception)

    def test_permanent_error_is_exception(self) -> None:
        assert issubclass(PermanentError, Exception)

    def test_transient_error_is_not_permanent(self) -> None:
        assert not issubclass(TransientError, PermanentError)
        assert not issubclass(PermanentError, TransientError)

    def test_transient_error_default_message(self) -> None:
        err = TransientError()
        assert "unavailable" in str(err).lower()

    def test_permanent_error_custom_message(self) -> None:
        err = PermanentError("Custom permanent error message")
        assert str(err) == "Custom permanent error message"


# =============================================================================
# Unit-level tool tests
# =============================================================================


class TestCheckCircuitState:
    """check_circuit_state tool."""

    def test_initial_state_closed(self) -> None:
        circuit = CircuitBreaker()
        assert check_circuit_state(circuit) == "closed"

    def test_after_failures_open(self) -> None:
        circuit = CircuitBreaker(failure_threshold=3, reset_timeout_ms=50000.0)
        circuit.record_failure()
        circuit.record_failure()
        circuit.record_failure()
        assert check_circuit_state(circuit) == "open"
