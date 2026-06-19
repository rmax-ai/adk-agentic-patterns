"""Tests for Pattern 11: Agent Handoff.

Covers:
- test_handoff_accepted — support transfers to refund, context preserved
- test_handoff_rejected — refund specialist rejects, fallback to support
- test_context_minimization — only relevant keys transferred
- test_narrower_permissions — refund specialist cannot access support tools
- test_handoff_audit — handoff event recorded
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
    FULL_CONTEXT_EXAMPLE,
    HANDOFF_RESPONSE_FIXTURES,
    RELEVANT_CONTEXT_KEYS,
    REFUND_AGENT,
    REFUND_TOOLS,
    SUPPORT_AGENT,
    SUPPORT_TOOLS,
    HandoffRequest,
    HandoffResponse,
    apply_context_minimisation,
    check_agent_permission,
    execute_agent_tool,
    minimise_context,
    run,
)

from adk_patterns.contracts import ExecutionStatus  # noqa: E402
from adk_patterns.shared import run_scope  # noqa: E402


# =============================================================================
# Scenario tests
# =============================================================================


def test_handoff_accepted() -> None:
    """Happy path: support transfers to refund specialist, context preserved."""
    result = run(scenario="handoff_accepted")
    assert result.status == ExecutionStatus.SUCCEEDED

    output = result.output
    assert output["conversation_context"]["agent"] == REFUND_AGENT
    assert output["conversation_context"]["status"] == "refund_handled"

    handoff_record = output["handoff_record"]
    assert handoff_record is not None
    assert handoff_record["request"]["from_agent"] == SUPPORT_AGENT
    assert handoff_record["request"]["to_agent"] == REFUND_AGENT
    assert handoff_record["response"]["accepted"] is True

    refund_result = output["refund_result"]
    assert refund_result is not None
    assert refund_result["handoff_accepted"] is True
    assert refund_result["specialist"] == REFUND_AGENT
    assert "refund_info" in refund_result
    assert "refund_result" in refund_result

    # Both model calls used: support decision + refund evaluation
    assert result.metrics["model_calls"] == 2


def test_handoff_rejected() -> None:
    """Refund specialist rejects the handoff, support falls back."""
    result = run(scenario="handoff_rejected")
    assert result.status == ExecutionStatus.SUCCEEDED

    output = result.output
    assert output["conversation_context"]["agent"] == SUPPORT_AGENT
    assert output["conversation_context"]["status"] == "handoff_fallback"

    handoff_record = output["handoff_record"]
    assert handoff_record is not None
    assert handoff_record["request"]["from_agent"] == SUPPORT_AGENT
    assert handoff_record["response"]["accepted"] is False

    refund_result = output["refund_result"]
    assert refund_result is not None
    assert refund_result["handoff_accepted"] is False
    assert refund_result["fallback_agent"] == SUPPORT_AGENT
    assert "rejection_reason" in refund_result
    assert "escalation" in refund_result

    # Both model calls used: support decision + refund evaluation
    assert result.metrics["model_calls"] == 2


def test_context_minimization() -> None:
    """Only relevant context keys are transferred to the refund specialist."""
    # Verify minimisation function strips irrelevant keys
    minimised = minimise_context(FULL_CONTEXT_EXAMPLE)

    # Relevant keys preserved
    assert minimised["customer_id"] == FULL_CONTEXT_EXAMPLE["customer_id"]
    assert minimised["invoice_id"] == FULL_CONTEXT_EXAMPLE["invoice_id"]
    assert minimised["issue_type"] == FULL_CONTEXT_EXAMPLE["issue_type"]
    assert minimised["request_text"] == FULL_CONTEXT_EXAMPLE["request_text"]

    # Sensitive/internal keys stripped
    assert "internal_notes" not in minimised
    assert "agent_session_id" not in minimised
    assert "support_tier" not in minimised
    assert "customer_email" not in minimised
    assert "customer_name" not in minimised

    # Every key in minimised is in the allowed set
    for key in minimised:
        assert key in RELEVANT_CONTEXT_KEYS

    # Full context had 10 keys, minimised only has the 4 relevant ones
    assert len(minimised) == 4

    # Run the scenario and verify the context was minimised
    result = run(scenario="context_minimization")
    handoff_request = result.output["handoff_record"]["request"]
    transferred_context = handoff_request["context"]

    # Only relevant keys should be in the transferred context
    for key in transferred_context:
        assert key in RELEVANT_CONTEXT_KEYS, f"Illegal key transferred: {key}"


def test_narrower_permissions() -> None:
    """Refund specialist cannot access support agent tools."""
    # Verify refund specialist can use its own tools
    assert check_agent_permission(REFUND_AGENT, "lookup_refund") is True
    assert check_agent_permission(REFUND_AGENT, "process_refund") is True

    # Verify refund specialist CANNOT use support tools
    assert check_agent_permission(REFUND_AGENT, "lookup_customer") is False
    assert check_agent_permission(REFUND_AGENT, "escalate") is False

    # Verify support agent can use its own tools
    assert check_agent_permission(SUPPORT_AGENT, "lookup_customer") is True
    assert check_agent_permission(SUPPORT_AGENT, "escalate") is True

    # Verify support agent CANNOT use refund tools
    assert check_agent_permission(SUPPORT_AGENT, "lookup_refund") is False
    assert check_agent_permission(SUPPORT_AGENT, "process_refund") is False

    # Verify runtime enforcement via execute_agent_tool
    with run_scope("test-permissions") as ctx:
        # Refund specialist using its own tool works
        result = execute_agent_tool(ctx, REFUND_AGENT, "lookup_refund", invoice_id="INV-001")
        assert result is not None

        # Refund specialist using support tool raises PermissionError
        with pytest.raises(PermissionError, match="not permitted"):
            execute_agent_tool(ctx, REFUND_AGENT, "lookup_customer")

        # Support agent using its own tool works
        result = execute_agent_tool(ctx, SUPPORT_AGENT, "lookup_customer", customer_id="CUST-001")
        assert result is not None


def test_handoff_audit() -> None:
    """Handoff events are recorded in the audit trail."""
    result = run(scenario="handoff_accepted")

    audit_events = result.audit_events
    actions = [e.action for e in audit_events]
    actors = [e.actor for e in audit_events]

    # Support agent model call recorded
    assert "model_call" in actions
    assert "support_agent" in actors

    # Refund specialist model call recorded
    assert "refund_specialist" in actors

    # Handoff event recorded — accepted
    handoff_events = [e for e in audit_events if e.actor == "handoff"]
    assert len(handoff_events) >= 1

    accepted_event = next((e for e in handoff_events if e.action == "accepted"), None)
    assert accepted_event is not None
    assert accepted_event.resource == "support->refund_specialist"
    assert accepted_event.outcome == "success"

    # Verify rejected scenario also has audit
    result_rejected = run(scenario="handoff_rejected")
    rejected_handoff_events = [
        e for e in result_rejected.audit_events
        if e.actor == "handoff" and e.action == "rejected"
    ]
    assert len(rejected_handoff_events) >= 1


# =============================================================================
# Unit tests for individual components
# =============================================================================


def test_contracts_handoff_request() -> None:
    """HandoffRequest contract fields are validated."""
    request = HandoffRequest(
        reason="Customer needs refund",
        context={"customer_id": "CUST-001"},
        from_agent="support",
        to_agent="refund_specialist",
    )
    assert request.reason == "Customer needs refund"
    assert request.context["customer_id"] == "CUST-001"
    assert request.from_agent == "support"
    assert request.to_agent == "refund_specialist"


def test_contracts_handoff_response_accepted() -> None:
    """HandoffResponse with accepted=True."""
    response = HandoffResponse(accepted=True, reason="Eligible for refund")
    assert response.accepted is True
    assert response.reason == "Eligible for refund"


def test_contracts_handoff_response_rejected() -> None:
    """HandoffResponse with accepted=False."""
    response = HandoffResponse(accepted=False, reason="Outside refund window")
    assert response.accepted is False
    assert response.reason == "Outside refund window"


def test_minimise_context_empty() -> None:
    """Empty dict stays empty."""
    assert minimise_context({}) == {}


def test_minimise_context_no_relevant_keys() -> None:
    """No relevant keys in input returns empty dict."""
    result = minimise_context({"foo": "bar", "baz": 123})
    assert result == {}


def test_minimise_context_only_relevant() -> None:
    """Only relevant keys are preserved when all are relevant."""
    source = {
        "customer_id": "CUST-001",
        "invoice_id": "INV-001",
        "issue_type": "refund",
    }
    result = minimise_context(source)
    assert result == source


def test_state_keys_present() -> None:
    """Verify conversation_context, handoff_record, refund_result are in output."""
    result = run(scenario="handoff_accepted")
    assert "conversation_context" in result.output
    assert "handoff_record" in result.output
    assert "refund_result" in result.output
    assert "conversation_context" in result.state_snapshot
    assert "handoff_record" in result.state_snapshot
    assert "refund_result" in result.state_snapshot


def test_budget_enforcement() -> None:
    """Verify budget limits are respected (max_model_calls=2)."""
    result = run(scenario="handoff_accepted")
    assert result.metrics["model_calls"] <= 2
    assert result.metrics["tool_calls"] <= 5

    result_rejected = run(scenario="handoff_rejected")
    assert result_rejected.metrics["model_calls"] <= 2
    assert result_rejected.metrics["tool_calls"] <= 5


def test_tool_permission_check_direct() -> None:
    """Direct permission checks work for all agent/tool combinations."""
    # All support tools
    for tool_name in SUPPORT_TOOLS:
        assert check_agent_permission(SUPPORT_AGENT, tool_name) is True
        assert check_agent_permission(REFUND_AGENT, tool_name) is False

    # All refund tools
    for tool_name in REFUND_TOOLS:
        assert check_agent_permission(REFUND_AGENT, tool_name) is True
        assert check_agent_permission(SUPPORT_AGENT, tool_name) is False

    # Unknown agent
    assert check_agent_permission("unknown_agent", "lookup_customer") is False

    # Unknown tool
    assert check_agent_permission(SUPPORT_AGENT, "nonexistent_tool") is False


def test_handoff_rejected_fallback_uses_support() -> None:
    """Rejected handoff leads to support agent executing escalate tool."""
    result = run(scenario="handoff_rejected")
    refund_result = result.output["refund_result"]
    assert refund_result["handoff_accepted"] is False
    assert refund_result["fallback_agent"] == SUPPORT_AGENT
    assert refund_result["escalation"]["status"] == "escalated"
    assert refund_result["escalation"]["priority"] == "high"


def test_handoff_accepted_uses_refund_tools() -> None:
    """Accepted handoff leads to refund specialist executing refund tools."""
    result = run(scenario="handoff_accepted")
    refund_result = result.output["refund_result"]
    assert refund_result["refund_info"]["eligible"] is True
    assert refund_result["refund_info"]["invoice_id"] == "INV-001"
    assert refund_result["refund_result"]["status"] == "processed"


def test_tool_execution_audit() -> None:
    """Tool calls are recorded in audit events."""
    result = run(scenario="handoff_accepted")
    tool_events = [e for e in result.audit_events if e.action == "tool_call"]
    # Should have at least lookup_refund + process_refund
    assert len(tool_events) >= 2

    tool_resources = [e.resource or "" for e in tool_events]
    assert any("refund_lookup:" in r for r in tool_resources)
    assert any("refund_process:" in r for r in tool_resources)


def test_handoff_fixture_accept_exists() -> None:
    """The refund_accept fixture exists and is configured correctly."""
    fixture = HANDOFF_RESPONSE_FIXTURES.get("refund_accept")
    assert fixture is not None
    assert fixture.accepted is True
    assert fixture.reason


def test_handoff_fixture_reject_exists() -> None:
    """The refund_reject fixture exists and is configured correctly."""
    fixture = HANDOFF_RESPONSE_FIXTURES.get("refund_reject")
    assert fixture is not None
    assert fixture.accepted is False
    assert fixture.reason


def test_apply_context_minimisation() -> None:
    """apply_context_minimisation wraps minimise_context correctly."""
    result = apply_context_minimisation(FULL_CONTEXT_EXAMPLE)
    expected = minimise_context(FULL_CONTEXT_EXAMPLE)
    assert result == expected
