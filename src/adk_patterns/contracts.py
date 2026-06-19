"""Core contracts and types shared across all patterns.

Every model-generated artifact that crosses a boundary must use these typed contracts.
No unchecked natural-language arguments are passed directly into side-effecting functions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    """Terminal status of a pattern run."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"
    NEEDS_APPROVAL = "needs_approval"
    BUDGET_EXHAUSTED = "budget_exhausted"
    PARTIAL = "partial"


class RunBudget(BaseModel):
    """Execution budget constraints for bounded execution.

    Every loop, agent run, or workflow must have explicit budgets.
    When a budget is exhausted, execution terminates with status BUDGET_EXHAUSTED.
    """

    max_model_calls: int = Field(default=20, ge=0, description="Maximum model invocations")
    max_tool_calls: int = Field(default=50, ge=0, description="Maximum tool invocations")
    max_iterations: int = Field(default=10, ge=0, description="Maximum loop iterations")
    timeout_seconds: float = Field(default=60.0, ge=0, description="Wall-clock timeout")
    max_synthetic_tokens: int = Field(default=100000, ge=0, description="Maximum synthetic tokens")


class AuditEvent(BaseModel):
    """Immutable audit record of an action within a pattern run."""

    event_id: str = Field(description="Unique event identifier")
    trace_id: str = Field(description="Correlation ID for the full run")
    actor: str = Field(description="Component that performed the action")
    action: str = Field(description="Action performed (e.g., tool_call, model_call, state_write)")
    resource: str | None = Field(default=None, description="Resource acted upon")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the event occurred",
    )
    outcome: str = Field(description="Result: success, failure, rejected, etc.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional context")


class ToolInvocationRecord(BaseModel):
    """Record of a single tool call with validated arguments."""

    tool_name: str
    validated_arguments: dict[str, Any] = Field(default_factory=dict)
    result_summary: dict[str, Any] | None = None
    error_type: str | None = None
    duration_ms: float = 0.0


class PatternRunResult(BaseModel):
    """Complete result of a pattern execution run."""

    pattern: str = Field(description="Pattern name (e.g., 'prompt-chaining')")
    scenario: str = Field(default="default", description="Scenario name")
    status: ExecutionStatus
    output: Any = Field(default=None, description="Primary output of the pattern")
    state_snapshot: dict[str, Any] = Field(default_factory=dict)
    audit_events: list[AuditEvent] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    failure_reason: str | None = None
    execution_mode: str = Field(default="offline", description="offline or live")


class PatternMetadata(BaseModel):
    """Metadata describing an agentic pattern for the registry and comparison matrix."""

    name: str = Field(description="Pattern identifier (e.g., 'prompt-chaining')")
    display_name: str = Field(description="Human-readable name")
    phase: int = Field(description="Implementation phase (1-6)")
    description: str = Field(description="What problem this pattern solves")
    autonomy_level: int = Field(
        ge=0, le=10, description="Autonomy escalation level (0=deterministic, 10=fully autonomous)"
    )
    # Comparison matrix dimensions
    determinism: int = Field(ge=0, le=10)
    adaptability: int = Field(ge=0, le=10)
    state_complexity: int = Field(ge=0, le=10)
    coordination_complexity: int = Field(ge=0, le=10)
    testability: int = Field(ge=0, le=10)
    failure_containment: int = Field(ge=0, le=10)
    security_isolation: int = Field(ge=0, le=10)
    latency: str = Field(description="Expected latency category: low, medium, high")
    token_consumption: str = Field(description="Expected token usage: low, medium, high")
    resumability: bool = Field(default=False)
    human_controllability: int = Field(ge=0, le=10)
    operational_burden: int = Field(ge=0, le=10)
    recommended_use_cases: list[str] = Field(default_factory=list)
    reasons_not_to_use: list[str] = Field(default_factory=list)
    related_patterns: list[str] = Field(default_factory=list)
