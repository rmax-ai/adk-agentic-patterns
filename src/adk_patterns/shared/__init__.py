"""Shared runner, state management, retry, audit, and trace infrastructure.

All examples import from here — never from another example directory.
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator

from contextlib import contextmanager
from dataclasses import dataclass, field

import structlog

from adk_patterns.contracts import (
    AuditEvent,
    ExecutionStatus,
    PatternRunResult,
    RunBudget,
    ToolInvocationRecord,
)

logger = structlog.get_logger(__name__)


# -- Run context ------------------------------------------------------------


@dataclass
class RunContext:
    """Holds the execution context for a single pattern run.

    Tracks budgets, audit events, tool invocations, and state transitions.
    """

    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    pattern: str = ""
    scenario: str = "default"
    execution_mode: str = "offline"

    # Budget tracking
    budget: RunBudget = field(default_factory=RunBudget)
    model_calls: int = 0
    tool_calls: int = 0
    iterations: int = 0
    synthetic_tokens: int = 0
    start_time: float = field(default_factory=time.monotonic)

    # Records
    audit_events: list[AuditEvent] = field(default_factory=list)
    tool_records: list[ToolInvocationRecord] = field(default_factory=list)
    state_snapshots: list[dict[str, Any]] = field(default_factory=list)

    # Termination
    status: ExecutionStatus = ExecutionStatus.SUCCEEDED
    failure_reason: str | None = None
    output: Any = None

    def check_budget(self) -> ExecutionStatus | None:
        """Check if any budget is exhausted. Returns status if so, None otherwise."""
        if self.model_calls >= self.budget.max_model_calls:
            return ExecutionStatus.BUDGET_EXHAUSTED
        if self.tool_calls >= self.budget.max_tool_calls:
            return ExecutionStatus.BUDGET_EXHAUSTED
        if self.iterations >= self.budget.max_iterations:
            return ExecutionStatus.BUDGET_EXHAUSTED
        elapsed = time.monotonic() - self.start_time
        if elapsed >= self.budget.timeout_seconds:
            return ExecutionStatus.BUDGET_EXHAUSTED
        if self.synthetic_tokens >= self.budget.max_synthetic_tokens:
            return ExecutionStatus.BUDGET_EXHAUSTED
        return None

    def record_model_call(self, tokens: int = 0) -> None:
        """Record a model invocation."""
        self.model_calls += 1
        self.synthetic_tokens += tokens

    def record_tool_call(self, record: ToolInvocationRecord) -> None:
        """Record a tool invocation."""
        self.tool_calls += 1
        self.tool_records.append(record)

    def record_iteration(self) -> None:
        """Record a loop iteration."""
        self.iterations += 1

    def audit(
        self,
        actor: str,
        action: str,
        resource: str | None = None,
        outcome: str = "success",
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Create and record an audit event."""
        event = AuditEvent(
            event_id=uuid.uuid4().hex[:16],
            trace_id=self.trace_id,
            actor=actor,
            action=action,
            resource=resource,
            outcome=outcome,
            metadata=metadata or {},
        )
        self.audit_events.append(event)
        return event

    def snapshot_state(self, state: dict[str, Any]) -> None:
        """Capture a state snapshot."""
        self.state_snapshots.append(dict(state))

    def mark_failed(self, reason: str) -> None:
        """Mark the run as failed."""
        self.status = ExecutionStatus.FAILED
        self.failure_reason = reason

    def mark_budget_exhausted(self) -> None:
        """Mark the run as budget-exhausted."""
        self.status = ExecutionStatus.BUDGET_EXHAUSTED
        self.failure_reason = "budget_exhausted"

    def to_result(self) -> PatternRunResult:
        """Produce a PatternRunResult from the current context."""
        return PatternRunResult(
            pattern=self.pattern,
            scenario=self.scenario,
            status=self.status,
            output=self.output,
            state_snapshot=self.state_snapshots[-1] if self.state_snapshots else {},
            audit_events=self.audit_events,
            metrics={
                "model_calls": float(self.model_calls),
                "tool_calls": float(self.tool_calls),
                "iterations": float(self.iterations),
                "synthetic_tokens": float(self.synthetic_tokens),
                "wall_clock_ms": (time.monotonic() - self.start_time) * 1000,
            },
            failure_reason=self.failure_reason,
            execution_mode=self.execution_mode,
        )


@contextmanager
def run_scope(
    pattern: str, scenario: str = "default", **budget_kwargs: Any
) -> Generator[Any, Any, Any]:
    """Context manager for a pattern run with automatic budget checking."""
    ctx = RunContext(
        pattern=pattern,
        scenario=scenario,
        budget=RunBudget(**budget_kwargs) if budget_kwargs else RunBudget(),
    )
    try:
        yield ctx
    except Exception as e:
        ctx.mark_failed(str(e))
        logger.exception("run_failed", pattern=pattern, scenario=scenario)
    if ctx.status == ExecutionStatus.BUDGET_EXHAUSTED:
        logger.warning("budget_exhausted", pattern=pattern, reason=ctx.failure_reason)
    return ctx


# -- Retry utilities --------------------------------------------------------


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    base_delay_ms: float = 100.0
    max_delay_ms: float = 5000.0
    backoff_multiplier: float = 2.0
    jitter_ms: float = 0.0  # Set to >0 for deterministic jitter in tests
    retry_on: tuple[type[Exception], ...] = (Exception,)


def compute_backoff(attempt: int, config: RetryConfig) -> float:
    """Compute backoff delay for a given attempt."""
    delay = min(
        config.base_delay_ms * (config.backoff_multiplier ** (attempt - 1)), config.max_delay_ms
    )
    return delay + config.jitter_ms


class RetryExhaustedError(Exception):
    """Raised when all retry attempts are exhausted."""

    def __init__(self, attempts: int, last_error: Exception | None = None):
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(f"Retry exhausted after {attempts} attempts")


# -- Circuit breaker --------------------------------------------------------


class CircuitBreaker:
    """Simple circuit breaker for transient failure protection."""

    def __init__(self, failure_threshold: int = 3, reset_timeout_ms: float = 5000.0):
        self.failure_threshold = failure_threshold
        self.reset_timeout_ms = reset_timeout_ms
        self._failures: int = 0
        self._last_failure_time: float = 0.0
        self._open: bool = False

    @property
    def is_open(self) -> bool:
        if not self._open:
            return False
        if time.monotonic() * 1000 - self._last_failure_time >= self.reset_timeout_ms:
            self._open = False
            self._failures = 0
            return False
        return True

    def record_failure(self) -> None:
        self._failures += 1
        self._last_failure_time = time.monotonic() * 1000
        if self._failures >= self.failure_threshold:
            self._open = True

    def record_success(self) -> None:
        self._failures = 0
        self._open = False

    def reset(self) -> None:
        self._failures = 0
        self._open = False
        self._last_failure_time = 0.0
