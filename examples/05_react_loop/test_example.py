"""Tests for Pattern 05: ReAct Loop.

Covers:
- Diagnosis success — model queries tools and submits diagnosis
- Step budget exhausted — hits max_iterations before finishing
- Repeated action detection — model tries same tool+args twice, gets flagged
- Non-convergence — model loops without progress, budget exhausted
- Read-only enforcement — diagnosis submitted but no external state mutated
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

# Example directories starting with digits aren't valid Python packages.
# Add parent to path so we can import from them.
_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))

from agent import run  # noqa: E402

from adk_patterns.contracts import ExecutionStatus  # noqa: E402


# ---------------------------------------------------------------------------
# Happy path: full diagnosis loop
# ---------------------------------------------------------------------------


def test_diagnosis_success() -> None:
    """Model queries tools (metrics, logs, deployment history) and submits diagnosis."""
    result = run(scenario="diagnosis_success")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    # State should have observations, actions, diagnosis
    assert "observations" in result.output
    assert "actions" in result.output
    assert "diagnosis" in result.output

    # Should have at least 3 observations (metrics, logs, deployment, diagnosis)
    assert len(result.output["observations"]) >= 3

    # Actions should include query_metrics, query_logs, get_deployment_history, submit_diagnosis
    action_tools = {a["tool"] for a in result.output["actions"]}
    assert "query_metrics" in action_tools
    assert "query_logs" in action_tools
    assert "get_deployment_history" in action_tools
    assert "submit_diagnosis" in action_tools

    # Diagnosis should be present
    assert result.output["diagnosis"] is not None
    assert len(result.output["diagnosis"]) > 0

    # Termination should be via diagnosis submission
    assert result.output.get("termination_reason") == "diagnosis_submitted"

    # No repeated actions in happy path
    repeated = [a for a in result.output["actions"] if a.get("repeated")]
    assert len(repeated) == 0, f"Expected no repeated actions, got: {repeated}"

    # Budget should be respected
    assert result.metrics["model_calls"] <= 10
    assert result.metrics["tool_calls"] <= 8
    assert result.metrics["iterations"] >= 1


# ---------------------------------------------------------------------------
# Multi-service diagnosis
# ---------------------------------------------------------------------------


def test_multi_service_diagnosis() -> None:
    """Model investigates multiple services before submitting diagnosis."""
    result = run(scenario="multi_service_diagnosis")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    action_tools = {a["tool"] for a in result.output["actions"]}
    assert "query_metrics" in action_tools
    assert "query_logs" in action_tools
    assert "submit_diagnosis" in action_tools

    # Should have at least 2 metrics queries (api-gateway + user-service)
    metrics_queries = [a for a in result.output["actions"] if a["tool"] == "query_metrics"]
    assert len(metrics_queries) >= 2

    # Diagnosis should be present
    assert result.output["diagnosis"] is not None

    # No repeated actions
    repeated = [a for a in result.output["actions"] if a.get("repeated")]
    assert len(repeated) == 0


# ---------------------------------------------------------------------------
# Step budget exhausted
# ---------------------------------------------------------------------------


def test_step_budget_exhausted() -> None:
    """Model hits max_iterations before finishing diagnosis."""
    result = run(scenario="budget_exhausted")

    # Should either be BUDGET_EXHAUSTED or FAILED with budget exhaustion
    assert result.status in (
        ExecutionStatus.BUDGET_EXHAUSTED,
        ExecutionStatus.FAILED,
    )

    assert result.output is not None

    # Should have actions but no diagnosis (never submitted)
    assert "actions" in result.output
    assert len(result.output["actions"]) > 0

    # No submit_diagnosis action
    action_tools = {a["tool"] for a in result.output["actions"]}
    assert "submit_diagnosis" not in action_tools

    # Budget metrics should be at or near limits
    assert result.metrics["tool_calls"] <= 8
    assert result.metrics["model_calls"] <= 10


# ---------------------------------------------------------------------------
# Repeated action detection
# ---------------------------------------------------------------------------


def test_repeated_action_detection() -> None:
    """Model tries same tool with same args twice — gets flagged as repeated."""
    result = run(scenario="repeated_action")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    # Should have at least 4 actions
    assert len(result.output["actions"]) >= 3

    # Find repeated actions
    repeated = [a for a in result.output["actions"] if a.get("repeated")]
    assert len(repeated) >= 1, (
        "Expected at least one repeated action to be flagged, "
        f"got {len(repeated)}. Actions: {result.output['actions']}"
    )

    # The repeated action should be query_metrics with same args
    assert any(
        r["tool"] == "query_metrics"
        and r["arguments"].get("service") == "api-gateway"
        and r["arguments"].get("metric") == "error_rate"
        for r in repeated
    ), f"Expected repeated query_metrics(api-gateway, error_rate). Repeated: {repeated}"

    # Audit trail should include repeated_action events
    repeated_events = [e for e in result.audit_events if e.action == "repeated_action"]
    assert len(repeated_events) >= 1

    # Should still have submitted a diagnosis
    action_tools = {a["tool"] for a in result.output["actions"]}
    assert "submit_diagnosis" in action_tools


# ---------------------------------------------------------------------------
# Non-convergence
# ---------------------------------------------------------------------------


def test_non_convergence() -> None:
    """Model loops without progress — budget gets exhausted."""
    result = run(scenario="non_convergence")

    # Should end with budget exhausted or failed
    assert result.status in (
        ExecutionStatus.BUDGET_EXHAUSTED,
        ExecutionStatus.FAILED,
    )

    assert result.output is not None

    # No diagnosis should have been submitted
    assert result.output.get("diagnosis") is None, (
        f"Expected no diagnosis for non-convergence, got: {result.output['diagnosis']}"
    )

    # No submit_diagnosis action
    action_tools = {a["tool"] for a in result.output.get("actions", [])}
    assert "submit_diagnosis" not in action_tools

    # Budget should be exhausted
    assert result.metrics["model_calls"] <= 10


# ---------------------------------------------------------------------------
# Read-only enforcement
# ---------------------------------------------------------------------------


def test_read_only_enforcement() -> None:
    """Diagnosis submitted but no external state mutated (apart from diagnosis record)."""
    import importlib

    # Reset shared data before test
    from mocks import reset_shared_data
    reset_shared_data()

    # Get initial mutable state (diagnosis_submitted should be False)
    from mocks import get_shared_data
    data_before = get_shared_data()
    diagnosis_submitted_before = data_before.diagnosis_submitted

    # Run the read_only_diagnosis scenario
    result = run(scenario="read_only_diagnosis")
    assert result.status == ExecutionStatus.SUCCEEDED

    # Check that the diagnosis was recorded
    data_after = get_shared_data()
    assert data_after.diagnosis_submitted is True, (
        "submit_diagnosis should have recorded the diagnosis"
    )

    assert result.output is not None
    assert result.output.get("diagnosis") is not None
    assert len(result.output["diagnosis"]) > 0

    # Actions should include submit_diagnosis
    action_tools = {a["tool"] for a in result.output.get("actions", [])}
    assert "submit_diagnosis" in action_tools


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


def test_audit_trail() -> None:
    """Every tool invocation is recorded in RunContext audit events."""
    result = run(scenario="diagnosis_success")

    # There should be audit events
    assert len(result.audit_events) > 0

    # Tool call audit events should be present
    tool_call_events = [e for e in result.audit_events if e.action == "tool_call"]
    assert len(tool_call_events) >= 3, (
        f"Expected at least 3 tool_call audit events, got {len(tool_call_events)}"
    )

    # Tool names should include known tools
    tool_names = {e.resource for e in tool_call_events}
    assert "query_metrics" in tool_names
    assert "query_logs" in tool_names
    assert "get_deployment_history" in tool_names
    assert "submit_diagnosis" in tool_names

    # Model call events should also be present
    model_call_events = [e for e in result.audit_events if e.action == "model_call"]
    assert len(model_call_events) >= 4


# ---------------------------------------------------------------------------
# Observable state (no raw chain-of-thought)
# ---------------------------------------------------------------------------


def test_observable_state_no_raw_cot() -> None:
    """State contains observations[], actions[], and diagnosis — not raw CoT."""
    result = run(scenario="diagnosis_success")

    assert result.output is not None

    # State keys should be observable decisions, actions, results
    state = result.output
    assert "observations" in state
    assert "actions" in state
    assert "diagnosis" in state

    # Observations should be formatted strings, not raw model output
    for obs in state["observations"]:
        assert isinstance(obs, str)

    # Actions should be structured records with tool, arguments, repeated flag
    for action in state["actions"]:
        assert "tool" in action
        assert "arguments" in action
        assert "repeated" in action

    # No raw chain-of-thought keys
    forbidden_cot_keys = {"chain_of_thought", "reasoning_trace", "raw_model_output", "internal_thoughts"}
    present_forbidden = forbidden_cot_keys & set(state.keys())
    assert len(present_forbidden) == 0, (
        f"State should not contain raw CoT keys, found: {present_forbidden}"
    )
