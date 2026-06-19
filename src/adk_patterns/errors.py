"""Error taxonomy for the pattern library."""

from __future__ import annotations


class PatternError(Exception):
    """Base error for all pattern library exceptions."""


class ModelError(PatternError):
    """Errors originating from model calls."""


class ModelTimeoutError(ModelError):
    """Model call timed out."""


class MalformedModelOutputError(ModelError):
    """Model returned output that failed schema validation."""


class NonConvergenceError(ModelError):
    """Model failed to converge within budget."""


class ToolError(PatternError):
    """Errors originating from tool calls."""


class ToolTimeoutError(ToolError):
    """Tool call timed out."""


class ToolExecutionError(ToolError):
    """Tool call failed during execution."""


class ToolUnavailableError(ToolError):
    """Requested tool is not available."""


class ValidationError(PatternError):
    """Schema or contract validation failure."""


class AuthorizationError(PatternError):
    """Action denied by policy or authorization check."""


class BudgetExhaustedError(PatternError):
    """Execution budget exhausted."""


class StateError(PatternError):
    """Invalid state transition or state key violation."""


class CircuitBreakerOpenError(PatternError):
    """Circuit breaker is open, requests blocked."""


class HandoffRejectedError(PatternError):
    """Agent handoff was rejected by the receiving agent."""


class ApprovalRequiredError(PatternError):
    """Action requires human approval that was not granted."""


class ApprovalTimeoutError(ApprovalRequiredError):
    """Human approval timed out."""


class IdempotencyViolationError(PatternError):
    """Non-idempotent operation was retried without idempotency key."""
