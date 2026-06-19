"""Tests for Pattern 01: Prompt Chaining.

Verifies:
- Success case: all three stages populate the correct state keys
- Malformed upstream: downstream stops when stage 1 validation fails
- All three stages populated with correct data
- State key isolation (no cross-contamination between stages)
- Budget enforcement (max_model_calls=3, max_iterations=0)
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

from adk_patterns.contracts import ExecutionStatus


# ── Success cases ────────────────────────────────────────────────────────


def test_success_security_breach() -> None:
    """Happy path: all three stages succeed with a security breach incident."""
    result = run(scenario="security_breach")
    assert result.status == ExecutionStatus.SUCCEEDED

    output = result.output
    assert output is not None

    # Stage 1 facts
    stage1 = output.get("stage1_facts", {})
    assert stage1["product"] == "API Gateway"
    assert stage1["issue_type"] == "security_breach"
    assert stage1["customer_tier"] == "enterprise"

    # Stage 2 severity
    stage2 = output.get("stage2_severity", {})
    assert stage2["severity"] == "critical"
    assert stage2["impact_score"] >= 0.9

    # Stage 3 summary
    stage3 = output.get("stage3_summary", {})
    assert isinstance(stage3["summary"], str)
    assert len(stage3["summary"]) > 20
    assert isinstance(stage3["recommended_actions"], list)
    assert len(stage3["recommended_actions"]) > 0
    assert stage3["requires_escalation"] is True

    # Metrics
    assert result.metrics["model_calls"] == 3
    assert result.metrics["tool_calls"] == 0
    assert result.metrics["iterations"] == 0


def test_success_latency_outage() -> None:
    """Happy path: latency outage incident."""
    result = run(scenario="latency_outage")
    assert result.status == ExecutionStatus.SUCCEEDED

    output = result.output
    assert output is not None

    stage1 = output.get("stage1_facts", {})
    assert stage1["product"] == "Database Service"
    assert stage1["issue_type"] == "latency_outage"

    stage2 = output.get("stage2_severity", {})
    assert stage2["severity"] == "high"

    stage3 = output.get("stage3_summary", {})
    assert stage3["requires_escalation"] is False


def test_success_degraded_performance() -> None:
    """Happy path: degraded performance incident."""
    result = run(scenario="degraded_performance")
    assert result.status == ExecutionStatus.SUCCEEDED

    output = result.output
    assert output is not None

    stage1 = output.get("stage1_facts", {})
    assert stage1["product"] == "Content Delivery Network"
    assert stage1["issue_type"] == "degraded_performance"

    stage2 = output.get("stage2_severity", {})
    assert stage2["severity"] == "medium"

    stage3 = output.get("stage3_summary", {})
    assert stage3["requires_escalation"] is False


# ── Malformed upstream ────────────────────────────────────────────────────


def test_malformed_upstream_stops_downstream() -> None:
    """When stage 1 output fails validation, stages 2 and 3 must not execute.

    The 'malformed_facts' fixture returns a response missing the required
    'product' field, which should cause IncidentFacts validation to fail
    in stage 1, preventing stages 2 and 3 from running.
    """
    result = run(scenario="malformed_facts")
    assert result.status == ExecutionStatus.FAILED

    assert result.failure_reason is not None
    assert "Stage 1" in result.failure_reason
    assert "validation failed" in result.failure_reason or "schema validation" in result.failure_reason

    # Only stage 1 should have consumed a model call
    assert result.metrics["model_calls"] == 1

    # Stage 2 and 3 should NOT have run
    output = result.output or {}
    assert "stage2_severity" not in output or output.get("stage2_severity") == "validation_failed"


# ── State key isolation ───────────────────────────────────────────────────


def test_all_three_stages_populated() -> None:
    """All three output state keys must be present on success."""
    result = run(scenario="security_breach")
    assert result.status == ExecutionStatus.SUCCEEDED

    output = result.output
    assert output is not None
    assert "stage1_facts" in output
    assert "stage2_severity" in output
    assert "stage3_summary" in output

    # Each key is a separate dict with its own schema
    assert isinstance(output["stage1_facts"], dict)
    assert isinstance(output["stage2_severity"], dict)
    assert isinstance(output["stage3_summary"], dict)

    # Verify fields from each stage don't leak into other stages
    stage1_keys = {"product", "issue_type", "customer_tier", "description"}
    stage2_keys = {"severity", "impact_score", "affected_users_estimate", "business_impact"}
    stage3_keys = {"summary", "recommended_actions", "notified_stakeholders", "requires_escalation"}

    assert stage1_keys.issubset(output["stage1_facts"].keys())
    assert stage2_keys.issubset(output["stage2_severity"].keys())
    assert stage3_keys.issubset(output["stage3_summary"].keys())


def test_state_key_isolation() -> None:
    """Stage 1 keys should NOT appear in stage 2/3, and vice versa."""
    result = run(scenario="security_breach")
    assert result.status == ExecutionStatus.SUCCEEDED

    output = result.output
    assert output is not None

    stage1 = output["stage1_facts"]
    stage2 = output["stage2_severity"]
    stage3 = output["stage3_summary"]

    # Stage 1 fields that belong only to stage 1
    assert "product" in stage1
    assert "issue_type" in stage1
    assert "product" not in stage2
    assert "product" not in stage3

    # Stage 2 fields that belong only to stage 2
    assert "severity" in stage2
    assert "impact_score" in stage2
    assert "severity" not in stage1
    assert "severity" not in stage3

    # Stage 3 fields that belong only to stage 3
    assert "summary" in stage3
    assert "recommended_actions" in stage3
    assert "summary" not in stage1
    assert "summary" not in stage2


# ── Audit / Budget enforcement ────────────────────────────────────────────


def test_audit_events_present() -> None:
    """Audit events from all three stages are recorded on success."""
    result = run(scenario="security_breach")
    assert result.status == ExecutionStatus.SUCCEEDED
    assert len(result.audit_events) >= 6  # 3 model_calls + 3 model_responses

    actors = {e.actor for e in result.audit_events}
    assert "stage1" in actors
    assert "stage2" in actors
    assert "stage3" in actors

    assert any(e.action == "model_call" for e in result.audit_events)
    assert any(e.action == "model_response" for e in result.audit_events)


def test_budget_enforcement() -> None:
    """max_model_calls=3 and max_iterations=0 are respected."""
    result = run(scenario="security_breach")
    assert result.metrics["model_calls"] == 3
    assert result.metrics["iterations"] == 0
    assert result.metrics["tool_calls"] == 0
