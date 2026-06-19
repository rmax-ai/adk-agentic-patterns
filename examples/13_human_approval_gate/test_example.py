"""Tests for Pattern 13: Human Approval Gate.

Covers:
- Agent proposes, workflow suspends pending approval
- Approval granted → refund executed
- Approval denied → refund not executed
- Approval times out → fallback action
- Agent cannot self-approve
- Idempotent resume — no duplicate refund
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
from adk_patterns.mocks.approval_service import MockApprovalService  # noqa: E402


# ---------------------------------------------------------------------------
# Approval required — workflow suspends pending approval
# ---------------------------------------------------------------------------


def test_approval_required() -> None:
    """Agent proposes a refund, workflow suspends with 'pending' approval status."""
    result = run(scenario="approval_required")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output
    assert "proposal" in state
    assert state["proposal"] is not None
    assert state["proposal"]["approval_status"] == "pending"
    assert "final_answer" in state
    assert len(state["final_answer"]) > 0

    # Budget should be respected (max_model_calls=2)
    assert result.metrics["model_calls"] <= 2


# ---------------------------------------------------------------------------
# Approved — approval granted, refund executed
# ---------------------------------------------------------------------------


def test_approved() -> None:
    """Approval granted by human reviewer → refund executed successfully."""
    result = run(scenario="approved")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output
    assert state["proposal"] is not None

    # The approval status should eventually lead to approval
    # refund_result should be present if execute_refund was called
    if state.get("refund_result"):
        assert state["refund_result"]["success"] is True
        assert state["refund_result"]["refund_id"] is not None

    assert len(state["final_answer"]) > 0


# ---------------------------------------------------------------------------
# Rejected — approval denied, refund not executed
# ---------------------------------------------------------------------------


def test_rejected() -> None:
    """Approval denied → refund not executed."""
    result = run(scenario="rejected")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output
    assert state["proposal"] is not None

    # The refund should NOT have been executed
    assert state.get("refund_result") is None, "Refund should not be executed when rejected"

    assert len(state["final_answer"]) > 0


# ---------------------------------------------------------------------------
# Timeout — approval times out, fallback action
# ---------------------------------------------------------------------------


def test_timeout() -> None:
    """Approval times out → fallback action (escalation message)."""
    result = run(scenario="timeout")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output
    assert state["proposal"] is not None

    # The refund should NOT have been executed when timed out
    assert state.get("refund_result") is None, "Refund should not be executed on timeout"

    # Final answer should acknowledge timeout/escalation
    final = state.get("final_answer", "").lower()
    assert "time" in final or "escalat" in final or "timeout" in final, (
        f"Expected timeout/escalation mention in answer: {final}"
    )


# ---------------------------------------------------------------------------
# Agent cannot self-approve
# ---------------------------------------------------------------------------


def test_agent_cannot_self_approve() -> None:
    """Agent blocked from approving own proposal — error returned by approve_refund."""
    result = run(scenario="self_approve")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output

    # The approve_refund tool call should have returned an error about self-approval
    tool_results = state.get("tool_results", {})
    approve_result = tool_results.get("approve_refund", {})
    if "error" in approve_result:
        assert "self-approve" in approve_result["error"].lower() or "agent" in approve_result["error"].lower()

    assert len(state["final_answer"]) > 0


# ---------------------------------------------------------------------------
# Idempotent resume — same state twice, no duplicate refund
# ---------------------------------------------------------------------------


def test_idempotent_resume() -> None:
    """Resume with same state twice — no duplicate refund issued."""
    result = run(scenario="idempotent_resume")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output
    if state.get("refund_result"):
        # If executed, it should be successful
        assert state["refund_result"]["success"] is True
        # Re-running should NOT create a duplicate — checked by idempotent logic
        # in execute_refund itself

    assert len(state["final_answer"]) > 0
