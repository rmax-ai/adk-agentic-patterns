"""Tests for Pattern 09: Sequential Specialists.

Verifies:
- Valid claim: all 4 stages execute and populate the correct state keys
- Ineligible claim: stops at eligibility stage (stages 3 and 4 do not run)
- Fraud detected: stops at fraud screening stage (stage 4 does not run)
- Stage isolation: each stage owns its own state keys, no cross-contamination
- Budget enforcement (max_model_calls=4, max_iterations=0)
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


# ── Valid claim (all 4 stages) ──────────────────────────────────────────────


def test_valid_claim_auto() -> None:
    """Happy path: all 4 stages succeed for a valid auto claim."""
    result = run(scenario="valid_auto")
    assert result.status == ExecutionStatus.SUCCEEDED

    output = result.output
    assert output is not None

    # Stage 1: Extraction
    stage1 = output.get("extracted_claim", {})
    assert stage1["claim_id"] == "CLM-2026-001"
    assert stage1["policy_number"] == "POL-AUTO-88723"
    assert stage1["claimant_name"] == "Jane Doe"
    assert stage1["incident_type"] == "auto_accident"
    assert stage1["amount_claimed"] == 3500.00

    # Stage 2: Eligibility
    stage2 = output.get("eligibility_result", {})
    assert stage2["is_eligible"] is True
    assert stage2["eligible_amount"] == 3500.00
    assert stage2["deductible"] == 500.00

    # Stage 3: Fraud Screening
    stage3 = output.get("fraud_result", {})
    assert stage3["is_suspicious"] is False
    assert stage3["risk_score"] < 0.5
    assert stage3["recommendation"] == "approve"

    # Stage 4: Explanation
    stage4 = output.get("explanation", {})
    assert isinstance(stage4["summary"], str)
    assert len(stage4["summary"]) > 20
    assert stage4["payment_amount"] == 3000.00
    assert isinstance(stage4["next_steps"], list)
    assert len(stage4["next_steps"]) > 0

    # Metrics
    assert result.metrics["model_calls"] == 4
    assert result.metrics["tool_calls"] == 0
    assert result.metrics["iterations"] == 0


def test_valid_claim_property() -> None:
    """Happy path: all 4 stages succeed for a valid property damage claim."""
    result = run(scenario="valid_property")
    assert result.status == ExecutionStatus.SUCCEEDED

    output = result.output
    assert output is not None

    stage1 = output.get("extracted_claim", {})
    assert stage1["claim_id"] == "CLM-2026-002"
    assert stage1["incident_type"] == "property_damage"

    stage2 = output.get("eligibility_result", {})
    assert stage2["is_eligible"] is True

    stage3 = output.get("fraud_result", {})
    assert stage3["is_suspicious"] is False

    stage4 = output.get("explanation", {})
    assert stage4["payment_amount"] == 7200.00

    assert result.metrics["model_calls"] == 4


# ── Ineligible claim (stops at eligibility) ──────────────────────────────


def test_ineligible_claim_stops_at_eligibility() -> None:
    """When Stage 2 returns is_eligible=False, stages 3 and 4 must not run."""
    result = run(scenario="ineligible")
    assert result.status == ExecutionStatus.SUCCEEDED

    output = result.output
    assert output is not None

    # Stage 1 should have completed
    assert "extracted_claim" in output
    assert output["extracted_claim"]["claim_id"] == "CLM-2026-003"

    # Stage 2 should have completed with ineligible verdict
    assert "eligibility_result" in output
    assert output["eligibility_result"]["is_eligible"] is False
    assert output["eligibility_result"]["eligible_amount"] == 0.0

    # Stages 3 and 4 should NOT have run
    assert "fraud_result" not in output
    assert "explanation" not in output

    # Only 2 model calls (stages 1 and 2)
    assert result.metrics["model_calls"] == 2
    assert result.metrics["tool_calls"] == 0
    assert result.metrics["iterations"] == 0


# ── Fraud detected (stops at fraud screening) ────────────────────────────


def test_fraud_detected_stops_at_fraud() -> None:
    """When Stage 3 returns is_suspicious=True, stage 4 must not run."""
    result = run(scenario="fraud_suspicious")
    assert result.status == ExecutionStatus.SUCCEEDED

    output = result.output
    assert output is not None

    # Stage 1 should have completed
    assert "extracted_claim" in output
    assert output["extracted_claim"]["claim_id"] == "CLM-2026-004"

    # Stage 2 should have completed
    assert "eligibility_result" in output
    assert output["eligibility_result"]["is_eligible"] is True

    # Stage 3 should have completed with suspicious verdict
    assert "fraud_result" in output
    assert output["fraud_result"]["is_suspicious"] is True
    assert output["fraud_result"]["risk_score"] > 0.5
    assert output["fraud_result"]["recommendation"] == "escalate"
    assert len(output["fraud_result"]["flags"]) > 0

    # Stage 4 should NOT have run
    assert "explanation" not in output

    # Only 3 model calls (stages 1, 2, and 3)
    assert result.metrics["model_calls"] == 3


# ── Stage isolation ──────────────────────────────────────────────────────


def test_all_four_stages_populated() -> None:
    """All four output state keys must be present on success."""
    result = run(scenario="valid_auto")
    assert result.status == ExecutionStatus.SUCCEEDED

    output = result.output
    assert output is not None
    assert "extracted_claim" in output
    assert "eligibility_result" in output
    assert "fraud_result" in output
    assert "explanation" in output

    # Each key is a separate dict with its own schema
    assert isinstance(output["extracted_claim"], dict)
    assert isinstance(output["eligibility_result"], dict)
    assert isinstance(output["fraud_result"], dict)
    assert isinstance(output["explanation"], dict)


def test_stage_isolation() -> None:
    """Each stage's keys should not leak into another stage's output."""
    result = run(scenario="valid_auto")
    assert result.status == ExecutionStatus.SUCCEEDED

    output = result.output
    assert output is not None

    extraction_keys = {"claim_id", "policy_number", "claimant_name", "incident_date", "incident_type", "description",
                       "amount_claimed"}
    eligibility_keys = {"is_eligible", "eligible_amount", "reason", "deductible"}
    fraud_keys = {"is_suspicious", "risk_score", "flags", "recommendation"}
    explanation_keys = {"summary", "coverage_details", "payment_amount", "next_steps"}

    stage1 = output["extracted_claim"]
    stage2 = output["eligibility_result"]
    stage3 = output["fraud_result"]
    stage4 = output["explanation"]

    # Verify each stage contains its own keys
    assert extraction_keys.issubset(stage1.keys())
    assert eligibility_keys.issubset(stage2.keys())
    assert fraud_keys.issubset(stage3.keys())
    assert explanation_keys.issubset(stage4.keys())

    # Verify no cross-contamination
    assert "claim_id" in stage1
    assert "claim_id" not in stage2
    assert "claim_id" not in stage3
    assert "claim_id" not in stage4

    assert "is_eligible" in stage2
    assert "is_eligible" not in stage1
    assert "is_eligible" not in stage3
    assert "is_eligible" not in stage4

    assert "is_suspicious" in stage3
    assert "is_suspicious" not in stage1
    assert "is_suspicious" not in stage2
    assert "is_suspicious" not in stage4

    assert "summary" in stage4
    assert "summary" not in stage1
    assert "summary" not in stage2
    assert "summary" not in stage3


# ── Audit / Budget enforcement ──────────────────────────────────────────────


def test_audit_events_present() -> None:
    """Audit events from all four stages are recorded on success."""
    result = run(scenario="valid_auto")
    assert result.status == ExecutionStatus.SUCCEEDED
    assert len(result.audit_events) >= 8  # 4 model_calls + 4 model_responses

    actors = {e.actor for e in result.audit_events}
    assert "extraction" in actors
    assert "eligibility" in actors
    assert "fraud_screening" in actors
    assert "explanation" in actors

    assert any(e.action == "model_call" for e in result.audit_events)
    assert any(e.action == "model_response" for e in result.audit_events)


def test_budget_enforcement() -> None:
    """max_model_calls=4 and max_iterations=0 are respected."""
    result = run(scenario="valid_auto")
    assert result.metrics["model_calls"] == 4
    assert result.metrics["iterations"] == 0
    assert result.metrics["tool_calls"] == 0
