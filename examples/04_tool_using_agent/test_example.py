"""Tests for Pattern 04: Tool-Using Agent.

Covers:
- Single tool call (order status lookup)
- Multi-tool sequence (order + customer)
- Invalid argument type → error handled gracefully
- Unavailable tool request → error handled gracefully
- Audit trail — every tool call recorded in RunContext
- Read-only enforcement — tools don't modify external state
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


# ---------------------------------------------------------------------------
# Happy path: single tool call
# ---------------------------------------------------------------------------


def test_order_status_lookup() -> None:
    """Model calls get_order_status and returns a final answer."""
    result = run(scenario="order_status")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None
    assert "tool_results" in result.output
    assert "get_order_status" in result.output["tool_results"]
    assert "final_answer" in result.output
    assert len(result.output["final_answer"]) > 0

    # Budget should be respected
    assert result.metrics["model_calls"] <= 3
    assert result.metrics["tool_calls"] >= 1
    assert result.metrics["iterations"] >= 1


# ---------------------------------------------------------------------------
# Multi-tool sequence
# ---------------------------------------------------------------------------


def test_multi_tool() -> None:
    """Model calls multiple tools in sequence before returning answer."""
    result = run(scenario="multi_tool")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None
    tool_results = result.output["tool_results"]
    assert "get_order_status" in tool_results
    assert "get_customer_info" in tool_results
    assert len(result.output["final_answer"]) > 0

    # At least two tool calls should have been made
    assert result.metrics["tool_calls"] >= 2
    assert result.metrics["model_calls"] >= 2


# ---------------------------------------------------------------------------
# Error handling: invalid tool argument
# ---------------------------------------------------------------------------


def test_invalid_tool_arg() -> None:
    """Model provides wrong argument type → error handled gracefully."""
    result = run(scenario="invalid_arg")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None
    tool_results = result.output["tool_results"]

    # The tool call should have failed with a type error
    status_result = tool_results.get("get_order_status", {})
    assert "error" in status_result
    assert "error_type" in status_result

    # The agent should have produced a final answer acknowledging the error
    assert len(result.output["final_answer"]) > 0


# ---------------------------------------------------------------------------
# Error handling: unavailable tool
# ---------------------------------------------------------------------------


def test_unavailable_tool() -> None:
    """Model requests a non-existent tool → error handled gracefully."""
    result = run(scenario="unavailable_tool")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None
    tool_results = result.output["tool_results"]

    # Look for any tool result that has an error
    errors_found = any("error" in tr for tr in tool_results.values())
    assert errors_found, "Expected at least one tool error for unavailable tool"

    # The agent should have produced a final answer acknowledging the error
    assert len(result.output["final_answer"]) > 0


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


def test_audit_trail() -> None:
    """Every tool invocation is recorded in RunContext audit events."""
    result = run(scenario="multi_tool")

    # There should be audit events
    assert len(result.audit_events) > 0

    # Tool call audit events should be present
    tool_call_events = [e for e in result.audit_events if e.action == "tool_call"]
    assert len(tool_call_events) >= 2, (
        f"Expected at least 2 tool_call audit events, got {len(tool_call_events)}"
    )

    # Tool names should match known tools
    tool_names = {e.resource for e in tool_call_events}
    assert "get_order_status" in tool_names
    assert "get_customer_info" in tool_names

    # Model call events should also be present
    model_call_events = [e for e in result.audit_events if "model_call" in e.action or e.action == "model_call"]
    assert len(model_call_events) >= 2


# ---------------------------------------------------------------------------
# Read-only enforcement
# ---------------------------------------------------------------------------


def test_read_only_enforcement() -> None:
    """Tools don't modify external state — only read operations."""

    # Re-import agent module to access module-level state
    import importlib
    import agent as agent_mod
    importlib.reload(agent_mod)

    # Capture state before
    inv_before = len(agent_mod._inventory._orders)
    ship_before = len(agent_mod._shipment_data)
    cust_before = len(agent_mod._customer_data)

    # Run the multi-tool scenario (most comprehensive)
    result = agent_mod.run(scenario="multi_tool")
    assert result.status == ExecutionStatus.SUCCEEDED

    # Capture state after — should be unchanged
    inv_after = len(agent_mod._inventory._orders)
    ship_after = len(agent_mod._shipment_data)
    cust_after = len(agent_mod._customer_data)

    assert inv_after == inv_before, "Inventory state was modified by read-only tools"
    assert ship_after == ship_before, "Shipment state was modified by read-only tools"
    assert cust_after == cust_before, "Customer state was modified by read-only tools"
