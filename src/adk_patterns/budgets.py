"""Budget enforcement utilities.

Every loop and agent run must check budgets at boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass

from adk_patterns.contracts import ExecutionStatus, RunBudget


@dataclass
class BudgetTracker:
    """Tracks consumption against a RunBudget and signals exhaustion."""

    budget: RunBudget
    model_calls: int = 0
    tool_calls: int = 0
    iterations: int = 0
    synthetic_tokens: int = 0
    elapsed_seconds: float = 0.0

    def record_model_call(self, tokens: int = 0) -> ExecutionStatus | None:
        """Record a model call. Returns BUDGET_EXHAUSTED if over limit."""
        self.model_calls += 1
        self.synthetic_tokens += tokens
        return self._check()

    def record_tool_call(self) -> ExecutionStatus | None:
        """Record a tool call."""
        self.tool_calls += 1
        return self._check()

    def record_iteration(self) -> ExecutionStatus | None:
        """Record an iteration."""
        self.iterations += 1
        return self._check()

    def _check(self) -> ExecutionStatus | None:
        """Check all budgets."""
        if self.model_calls >= self.budget.max_model_calls:
            return ExecutionStatus.BUDGET_EXHAUSTED
        if self.tool_calls >= self.budget.max_tool_calls:
            return ExecutionStatus.BUDGET_EXHAUSTED
        if self.iterations >= self.budget.max_iterations:
            return ExecutionStatus.BUDGET_EXHAUSTED
        if self.synthetic_tokens >= self.budget.max_synthetic_tokens:
            return ExecutionStatus.BUDGET_EXHAUSTED
        return None

    @property
    def is_exhausted(self) -> bool:
        return self._check() is not None
