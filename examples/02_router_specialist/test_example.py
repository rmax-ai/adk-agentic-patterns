"""Tests for Pattern 02: Router-Specialist.

Covers:
- Correct routing to billing, account, and technical specialists
- Low-confidence fallback to general specialist
- Unknown/ambiguous route handling
- Rule-driven router variant
- Isolated tool sets per specialist
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

from agent import (  # noqa: E402
    CONFIDENCE_THRESHOLD,
    CONFUSION_MATRIX,
    RouterVerdict,
    check_tool_permission,
    handle_with_specialist,
    run,
)

from adk_patterns.contracts import ExecutionStatus


def test_billing_route() -> None:
    """Happy path: route a billing request to the billing specialist."""
    result = run(scenario="billing_route")
    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output["route_verdict"]["route"] == "billing"
    assert result.output["route_verdict"]["confidence"] >= 0.6
    assert result.output["specialist_output"]["specialist"] == "billing"
    assert result.metrics["model_calls"] == 1
    assert result.metrics["tool_calls"] == 2  # lookup_invoice + process_refund


def test_account_route() -> None:
    """Route an account request to the account specialist."""
    result = run(scenario="account_route")
    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output["route_verdict"]["route"] == "account"
    assert result.output["route_verdict"]["confidence"] >= 0.6
    assert result.output["specialist_output"]["specialist"] == "account"
    assert "reset_password" in result.output["specialist_output"]["tools_used"]


def test_technical_route() -> None:
    """Route a technical request to the technical specialist."""
    result = run(scenario="technical_route")
    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output["route_verdict"]["route"] == "technical"
    assert result.output["route_verdict"]["confidence"] >= 0.6
    assert result.output["specialist_output"]["specialist"] == "technical"
    assert "check_api_status" in result.output["specialist_output"]["tools_used"]


def test_low_confidence_fallback() -> None:
    """Confidence below threshold (0.6) routes to general specialist."""
    result = run(scenario="low_confidence")
    assert result.status == ExecutionStatus.SUCCEEDED
    # Original route was billing with 0.45 confidence, but fallback re-routes to general
    assert result.output["route_verdict"]["route"] == "general"
    assert result.output["route_verdict"]["confidence"] < 0.6
    assert result.output["specialist_output"]["specialist"] == "general"


def test_unknown_route() -> None:
    """Unknown route goes to fallback general specialist."""
    result = run(scenario="unknown_route")
    assert result.status == ExecutionStatus.SUCCEEDED
    # Original route is 'unknown_topic' with 0.35 confidence, fallback to general
    assert result.output["route_verdict"]["route"] == "general"
    assert result.output["specialist_output"]["specialist"] == "general"
    assert len(result.output["specialist_output"]["tools_used"]) == 0


def test_ambiguous_route() -> None:
    """Ambiguous query routes to general specialist."""
    result = run(scenario="ambiguous")
    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output["route_verdict"]["route"] == "general"
    assert result.output["specialist_output"]["specialist"] == "general"


def test_rule_driven_variant() -> None:
    """Deterministic keyword-based router without model call."""
    result = run(scenario="billing_route", use_rule_router=True)
    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output["route_verdict"]["route"] == "billing"
    assert result.output["specialist_output"]["specialist"] == "billing"
    # Rule-driven router does NOT make a model call
    assert result.metrics["model_calls"] == 0
    # But specialist still uses tools
    assert result.metrics["tool_calls"] >= 1


def test_isolated_tools() -> None:
    """Billing specialist cannot access technical tools."""
    # Verify technical specialist can use technical tools
    assert check_tool_permission("technical", "check_api_status") is True
    assert check_tool_permission("technical", "query_logs") is True

    # Verify billing specialist CANNOT use technical tools
    assert check_tool_permission("billing", "check_api_status") is False
    assert check_tool_permission("billing", "query_logs") is False
    assert check_tool_permission("billing", "process_refund") is True

    # Verify account specialist CANNOT use technical tools
    assert check_tool_permission("account", "query_logs") is False
    assert check_tool_permission("account", "reset_password") is True


def test_router_confusion_matrix() -> None:
    """Verify confusion-matrix scenarios are defined correctly."""
    for expected_specialist, verdict in CONFUSION_MATRIX.values():
        # Misrouted — the model chose the wrong specialist
        assert verdict.route != expected_specialist
        # But confidence is above threshold so it won't be re-routed
        assert verdict.confidence >= 0.6


def test_state_keys() -> None:
    """Verify route_verdict and specialist_output state keys are present."""
    result = run(scenario="billing_route")
    assert "route_verdict" in result.output
    assert "specialist_output" in result.output
    assert "route_verdict" in result.state_snapshot
    assert "specialist_output" in result.state_snapshot


def test_budget_enforcement() -> None:
    """Verify budget limits are respected."""
    result = run(scenario="billing_route")
    assert result.metrics["model_calls"] <= 2  # max_model_calls=2
    assert result.metrics["tool_calls"] <= 5  # max_tool_calls=5


def test_audit_events_present() -> None:
    """Audit events are recorded for routing and specialist dispatch."""
    result = run(scenario="billing_route")
    assert any(e.action == "model_call" for e in result.audit_events)
    assert any(e.action == "model_response" for e in result.audit_events)
    assert any(e.action == "dispatch" for e in result.audit_events)
