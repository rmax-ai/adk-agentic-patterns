"""Tests for Pattern 20: Dynamic Workflow.

Verifies:
- All 4 branches are reachable (schema_violation, missing_data, stale_data, unknown)
- Each branch records correct state transitions
- State transitions are recorded in state_snapshot
- Same input always produces the same branch (deterministic)
- Branch paths are correct per incident type
- Budget enforcement (max_model_calls=3, max_iterations=3)
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

from agent import run, _VALID_SCENARIOS  # noqa: E402

from adk_patterns.contracts import ExecutionStatus


# ── Individual branch tests ────────────────────────────────────────────────


def test_schema_violation_branch() -> None:
    """Schema violation is classified and routed to validate_schema branch."""
    result = run(scenario="schema_violation")
    assert result.status == ExecutionStatus.SUCCEEDED

    output = result.output
    assert output is not None

    # Classification
    assert output["incident_type"] == "schema_violation"
    assert output["classification"]["incident_type"] == "schema_violation"
    assert output["classification"]["confidence"] >= 0.9

    # Resolution
    resolution = output["resolution"]
    assert resolution["branch"] == "validate_schema"
    assert resolution["action"] == "constraint_validation"
    assert "constraints_checked" in resolution
    assert resolution["violations_found"] == 12
    assert "remediation" in resolution

    # Only 1 model call (classification only — no model-driven routing)
    assert result.metrics["model_calls"] == 1.0


def test_missing_data_branch() -> None:
    """Missing data is classified and routed to assess_completeness branch."""
    result = run(scenario="missing_data")
    assert result.status == ExecutionStatus.SUCCEEDED

    output = result.output
    assert output is not None

    assert output["incident_type"] == "missing_data"
    assert output["classification"]["incident_type"] == "missing_data"

    resolution = output["resolution"]
    assert resolution["branch"] == "assess_completeness"
    assert resolution["action"] == "gap_analysis"
    assert resolution["total_records"] == 47
    assert "missing_segments" in resolution
    assert "remediation" in resolution

    assert result.metrics["model_calls"] == 1.0


def test_stale_data_branch() -> None:
    """Stale data is classified and routed to check_freshness branch."""
    result = run(scenario="stale_data")
    assert result.status == ExecutionStatus.SUCCEEDED

    output = result.output
    assert output is not None

    assert output["incident_type"] == "stale_data"
    assert output["classification"]["incident_type"] == "stale_data"

    resolution = output["resolution"]
    assert resolution["branch"] == "check_freshness"
    assert resolution["action"] == "timestamp_validation"
    assert resolution["stale_hours"] == 6.5
    assert resolution["skus_affected"] == 234
    assert "remediation" in resolution

    assert result.metrics["model_calls"] == 1.0


def test_unknown_escalation() -> None:
    """Unknown incident type is escalated to human analyst."""
    result = run(scenario="unknown")
    assert result.status == ExecutionStatus.SUCCEEDED

    output = result.output
    assert output is not None

    assert output["incident_type"] == "unknown"
    assert output["classification"]["incident_type"] == "unknown"
    assert output["classification"]["confidence"] == 0.45

    resolution = output["resolution"]
    assert resolution["branch"] == "escalate_to_analyst"
    assert resolution["action"] == "human_escalation"
    assert resolution["escalation_level"] == "senior_data_analyst"
    assert len(resolution["required_investigation"]) >= 2
    assert "remediation" in resolution

    assert result.metrics["model_calls"] == 1.0


# ── Branch coverage ────────────────────────────────────────────────────────


def test_all_branches_coverage() -> None:
    """Run all 4 scenarios to prove every branch path is exercised."""
    scenarios = sorted(_VALID_SCENARIOS)
    exercised_branches = set()

    for scenario in scenarios:
        result = run(scenario=scenario)
        assert result.status == ExecutionStatus.SUCCEEDED
        assert result.output is not None

        branch = result.output["resolution"]["branch"]
        exercised_branches.add(branch)

    # All 4 branches must be exercised
    expected_branches = {
        "validate_schema",
        "assess_completeness",
        "check_freshness",
        "escalate_to_analyst",
    }
    assert exercised_branches == expected_branches, (
        f"Missing branches: {expected_branches - exercised_branches}"
    )
    assert len(exercised_branches) == 4


# ── State transitions ──────────────────────────────────────────────────────


def test_state_transitions_recorded() -> None:
    """State snapshot must contain transition events from classification to resolution."""
    result = run(scenario="schema_violation")
    assert result.status == ExecutionStatus.SUCCEEDED

    snap = result.state_snapshot
    assert isinstance(snap, dict)

    # State keys required by spec
    assert "incident_type" in snap
    assert "branch_path" in snap
    assert "transitions" in snap
    assert "resolution" in snap

    # Branch path must be a list with 3 entries (classification → branch → resolution)
    branch_path = snap["branch_path"]
    assert isinstance(branch_path, list)
    assert len(branch_path) == 3
    assert branch_path[0] == "classification"

    # Transitions must be recorded
    transitions = snap["transitions"]
    assert isinstance(transitions, list)
    assert len(transitions) >= 2
    assert transitions[0]["from"] == "classification"
    assert transitions[-1]["to"] == "resolution"
    assert all("reason" in t for t in transitions)


# ── Determinism ────────────────────────────────────────────────────────────


def test_deterministic_branching() -> None:
    """Same input must always produce the same branch (no model variance)."""
    # Run the same scenario 3 times
    results = [run(scenario="schema_violation") for _ in range(3)]

    outputs = [r.output for r in results]
    assert all(o is not None for o in outputs)

    # All runs must produce the same incident type and branch
    incident_types = {o["incident_type"] for o in outputs}
    branches = {o["resolution"]["branch"] for o in outputs}

    assert incident_types == {"schema_violation"}
    assert branches == {"validate_schema"}

    # Check that validation results are identical across runs
    violations = [o["resolution"]["violations_found"] for o in outputs]
    assert all(v == 12 for v in violations)


# ── Budget enforcement ─────────────────────────────────────────────────────


def test_budget_enforcement() -> None:
    """max_model_calls=3 and max_iterations=3 are respected."""
    result = run(scenario="schema_violation")
    assert result.metrics["model_calls"] == 1.0
    assert result.metrics["iterations"] == 2.0  # 1 classification + 1 branch
    assert result.metrics["tool_calls"] == 0.0
