"""Tests for Pattern 08: Bounded Loop Agent.

Tests cover:
- Loop converges within budget (all sections present after 2-3 iterations)
- Budget exhaustion returns partial result with BUDGET_EXHAUSTED status
- Early stop on pass when all sections are present on first draft
- Partial result includes missing_sections on exhaustion
- State keys (draft, missing_sections, iteration, status) persist in snapshots
- Section validation against required checklist at each iteration
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Example directories starting with digits aren't valid Python packages.
# Add parent to path so we can import from them.
_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))

from agent import run  # noqa: E402

from adk_patterns.contracts import ExecutionStatus  # noqa: E402


def test_converges() -> None:
    """Loop runs 2-3 iterations until all sections present and passes."""
    result = run(scenario="converges")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output
    assert state["status"] == "PASSED"
    assert len(state["missing_sections"]) == 0
    assert "executive_summary" in state["draft"].get("sections", {})
    assert "methodology" in state["draft"].get("sections", {})
    assert "findings" in state["draft"].get("sections", {})
    assert "recommendations" in state["draft"].get("sections", {})
    assert "signatures" in state["draft"].get("sections", {})

    # Should have completed in 2-3 iterations with 4-6 model calls
    assert result.metrics["iterations"] >= 2.0
    assert result.metrics["iterations"] <= 5.0
    assert result.metrics["model_calls"] >= 4.0
    assert result.metrics["model_calls"] <= 6.0
    assert result.metrics["tool_calls"] == 0.0


def test_budget_exhausted() -> None:
    """5 iterations hit, returns partial result with BUDGET_EXHAUSTED."""
    result = run(scenario="budget_exhausted")

    assert result.status == ExecutionStatus.BUDGET_EXHAUSTED
    assert result.output is not None

    state = result.output
    assert state["status"] == "BUDGET_EXHAUSTED"
    assert len(state["missing_sections"]) > 0
    assert result.failure_reason is not None
    assert "budget" in result.failure_reason.lower()


def test_stop_on_pass() -> None:
    """Completes early when all required sections pass on first draft."""
    result = run(scenario="stop_on_pass")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output
    assert state["status"] == "PASSED"
    assert len(state["missing_sections"]) == 0

    # Should complete in 1 iteration (2 model calls: draft + validate)
    assert result.metrics["iterations"] == 1.0
    assert result.metrics["model_calls"] == 2.0


def test_partial_result_on_exhaustion() -> None:
    """Partial report returned with missing_sections listed on exhaustion."""
    result = run(scenario="budget_exhausted")

    assert result.status == ExecutionStatus.BUDGET_EXHAUSTED
    assert result.output is not None

    state = result.output
    # Partial result should have a draft and missing sections
    assert "draft" in state
    assert "missing_sections" in state
    assert len(state["missing_sections"]) > 0

    # The draft should exist even if incomplete
    assert isinstance(state["draft"], dict)
    assert "sections" in state["draft"]


def test_state_keys_persist() -> None:
    """draft, missing_sections, iteration, and status are in state_snapshot."""
    result = run(scenario="converges")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output
    assert "draft" in state
    assert "missing_sections" in state
    assert "iteration" in state
    assert "status" in state

    # Verify snapshot matches
    snapshot = result.state_snapshot
    assert "draft" in snapshot
    assert "missing_sections" in snapshot
    assert "iteration" in snapshot
    assert "status" in snapshot


def test_section_validation() -> None:
    """Each iteration validates against the required checklist."""
    result = run(scenario="converges")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    # In the final state, no sections should be missing
    state = result.output
    assert len(state["missing_sections"]) == 0

    # The final draft should have all 5 required sections
    sections = state["draft"].get("sections", {})
    required = {"executive_summary", "methodology", "findings", "recommendations", "signatures"}
    present = set(sections.keys())
    missing = required - present
    assert len(missing) == 0, f"Missing sections: {missing}"

    # Verify the draft confirms complete=True
    assert state["draft"].get("complete") is True
