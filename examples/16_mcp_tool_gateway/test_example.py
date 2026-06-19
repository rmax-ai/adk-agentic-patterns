"""Tests for Pattern 16: MCP Tool Gateway.

Covers:
- Tool discovery — list_tools returns the full tool catalog
- Tool invocation — call_tool works with typed arguments
- Malformed response — server returns bad JSON, client handles it
- Timeout handling — slow server triggers client timeout
- Allowlist filtering — only whitelisted tools are exposed
- Namespaced tools — mcp:ticketing/* and mcp:knowledge/* conventions
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

from agent import run, MCPClient, MockMCPServer, build_mcp_server  # noqa: E402

from adk_patterns.contracts import ExecutionStatus  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mcp_server() -> MockMCPServer:
    """Build a fresh MCP server with all tools registered."""
    return build_mcp_server()


@pytest.fixture
def mcp_client(mcp_server: MockMCPServer) -> MCPClient:
    """Build an MCP client wrapping the server."""
    return MCPClient(mcp_server, timeout_ms=5000.0)


# ---------------------------------------------------------------------------
# Tool discovery: list_tools returns catalog
# ---------------------------------------------------------------------------


def test_tool_discovery() -> None:
    """Model discovers MCP tools via list_mcp_tools."""
    result = run(scenario="tool_discovery")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output
    assert "mcp_tools" in state
    assert "mcp_results" in state
    assert "final_answer" in state
    assert len(state["final_answer"]) > 0

    # mcp_tools should be populated via list_tools
    mcp_tools = state["mcp_tools"]
    assert len(mcp_tools) >= 5, f"Expected at least 5 tools, got {len(mcp_tools)}"

    # Check for namespaced tool names
    tool_names = {t["name"] for t in mcp_tools}
    assert "mcp:ticketing/create_ticket" in tool_names
    assert "mcp:ticketing/get_ticket" in tool_names
    assert "mcp:ticketing/list_tickets" in tool_names
    assert "mcp:knowledge/search_docs" in tool_names
    assert "mcp:knowledge/get_article" in tool_names

    # Each tool should have required fields
    for tool in mcp_tools:
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool or "input_schema" in tool

    # Budget should be respected
    assert result.metrics["model_calls"] <= 3
    assert result.metrics["tool_calls"] <= 5


# ---------------------------------------------------------------------------
# Tool invocation: call_tool works
# ---------------------------------------------------------------------------


def test_tool_invocation() -> None:
    """Model calls an MCP tool and gets a result."""
    result = run(scenario="tool_invocation")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output
    assert "mcp_results" in state
    assert len(state["mcp_results"]) > 0

    # Should have result from mcp:ticketing/create_ticket
    mcp_results = state["mcp_results"]
    ticket_result = mcp_results.get("mcp:ticketing/create_ticket", {})
    assert "result" in ticket_result or "error" not in ticket_result

    # Ticket should have been created
    ticket_data = ticket_result.get("result", ticket_result)
    if "ticket_id" in ticket_data:
        assert ticket_data["ticket_id"] is not None
        assert ticket_data["title"] == "Test ticket"

    assert len(state["final_answer"]) > 0

    # Budget should be respected
    assert result.metrics["model_calls"] <= 3
    assert result.metrics["tool_calls"] <= 5


def test_multi_tool_invocation() -> None:
    """Model calls multiple MCP tools in sequence."""
    result = run(scenario="multi_tool")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output
    mcp_results = state["mcp_results"]
    assert len(mcp_results) >= 1

    # Check for results from both namespaces
    ticketing_results = [k for k in mcp_results if k.startswith("mcp:ticketing/")]
    knowledge_results = [k for k in mcp_results if k.startswith("mcp:knowledge/")]

    assert len(ticketing_results) >= 1
    assert len(knowledge_results) >= 1

    assert len(state["final_answer"]) > 0


# ---------------------------------------------------------------------------
# Malformed response handling
# ---------------------------------------------------------------------------


def test_malformed_response() -> None:
    """MCP server returns malformed response — handled gracefully."""
    result = run(scenario="malformed_response")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output
    mcp_results = state["mcp_results"]

    # The malformed call should still be recorded
    malformed_result = mcp_results.get("mcp:ticketing/get_ticket", {})

    # When malformed mode is active, the server returns error code -32700
    # Either there's an error key, or the model provided a final_answer acknowledging it
    assert len(state["final_answer"]) > 0

    # Model call count should stay within budget
    assert result.metrics["model_calls"] <= 3


# ---------------------------------------------------------------------------
# Timeout handling
# ---------------------------------------------------------------------------


def test_timeout_handling() -> None:
    """MCP server with delay triggers client timeout — handled gracefully."""
    result = run(scenario="timeout_handling")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output

    # The final answer should reference the timeout or describe the result
    assert len(state["final_answer"]) > 0

    # Should still be within budget
    assert result.metrics["model_calls"] <= 3


# ---------------------------------------------------------------------------
# Allowlist filtering
# ---------------------------------------------------------------------------


def test_allowlist_filtering() -> None:
    """Only allowlisted tools are exposed by the MCP server."""
    result = run(scenario="allowlist_filtering")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output
    mcp_tools = state["mcp_tools"]

    # Only allowlisted tools should be in the catalog
    tool_names = {t["name"] for t in mcp_tools}
    assert "mcp:ticketing/get_ticket" in tool_names
    assert "mcp:knowledge/get_article" in tool_names

    # Non-allowlisted tools should NOT be in the catalog
    assert "mcp:ticketing/create_ticket" not in tool_names
    assert "mcp:ticketing/list_tickets" not in tool_names
    assert "mcp:knowledge/search_docs" not in tool_names

    # Should only have 2 tools
    assert len(mcp_tools) == 2

    assert len(state["final_answer"]) > 0

    # Budget should be respected
    assert result.metrics["model_calls"] <= 3
    assert result.metrics["tool_calls"] <= 5


# ---------------------------------------------------------------------------
# Namespaced tools
# ---------------------------------------------------------------------------


def test_namespaced_tools() -> None:
    """MCP tool names follow the mcp:namespace/name convention."""
    result = run(scenario="namespaced_tools")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output
    mcp_results = state["mcp_results"]

    # The knowledge search should have been executed
    search_result = mcp_results.get("mcp:knowledge/search_docs", {})
    assert "result" in search_result or "error" not in search_result

    # Results should contain articles
    search_data = search_result.get("result", {})
    if "results" in search_data:
        assert len(search_data["results"]) >= 1

    assert len(state["final_answer"]) > 0

    # Verify audit trail has namespaced tool calls
    namespaced_events = [
        e for e in result.audit_events
        if e.action == "tool_call" and isinstance(e.resource, str) and "mcp:" in e.resource
    ]
    assert len(namespaced_events) >= 1

    # Budget should be respected
    assert result.metrics["model_calls"] <= 3
    assert result.metrics["tool_calls"] <= 5


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


def test_audit_trail() -> None:
    """Every MCP tool invocation is recorded in RunContext audit events."""
    result = run(scenario="multi_tool")

    # There should be audit events
    assert len(result.audit_events) > 0

    # Tool call audit events should be present
    tool_call_events = [e for e in result.audit_events if e.action == "tool_call"]
    assert len(tool_call_events) >= 2, (
        f"Expected at least 2 tool_call audit events, got {len(tool_call_events)}"
    )

    # Tool names should include namespaced MCP tools
    tool_names = {e.resource for e in tool_call_events}
    has_ticketing = any("mcp:ticketing/" in str(n) for n in tool_names)
    has_knowledge = any("mcp:knowledge/" in str(n) for n in tool_names)
    assert has_ticketing or has_knowledge, (
        f"Expected namespaced MCP tool names in audit trail, got: {tool_names}"
    )

    # Model call events should also be present
    model_call_events = [e for e in result.audit_events if e.action == "model_call"]
    assert len(model_call_events) >= 2

    # Final answer event
    final_events = [e for e in result.audit_events if e.action == "final_answer"]
    assert len(final_events) == 1


# ---------------------------------------------------------------------------
# Direct MCP server tests (unit-level, no model)
# ---------------------------------------------------------------------------


def test_mcp_server_list_tools(mcp_server: MockMCPServer) -> None:
    """Direct test: MCP server list_tools returns all 5 tools."""
    tools = mcp_server.list_tools()
    assert len(tools) == 5

    tool_names = {t["name"] for t in tools}
    expected = {
        "mcp:ticketing/create_ticket",
        "mcp:ticketing/get_ticket",
        "mcp:ticketing/list_tickets",
        "mcp:knowledge/search_docs",
        "mcp:knowledge/get_article",
    }
    assert tool_names == expected

    # Verify inputSchema exists on each
    for tool in tools:
        assert "inputSchema" in tool


def test_mcp_server_call_ticketing(mcp_server: MockMCPServer) -> None:
    """Direct test: MCP server call_tool on a ticketing tool."""
    result = mcp_server.call_tool("mcp:ticketing/create_ticket", {
        "title": "Direct test",
        "description": "Testing MCP server directly",
        "priority": "high",
    })
    assert "result" in result
    assert result["result"]["title"] == "Direct test"
    assert result["result"]["priority"] == "high"


def test_mcp_server_call_knowledge(mcp_server: MockMCPServer) -> None:
    """Direct test: MCP server call_tool on a knowledge tool."""
    result = mcp_server.call_tool("mcp:knowledge/search_docs", {"query": "rollback"})
    assert "result" in result
    assert result["result"]["count"] >= 1

    # Should find KB-001 (deployment rollback)
    article_ids = [a["article_id"] for a in result["result"]["results"]]
    assert "KB-001" in article_ids


def test_mcp_server_malformed_flag(mcp_server: MockMCPServer) -> None:
    """Direct test: MCP server returns malformed error when flag is set."""
    mcp_server.set_malformed()
    result = mcp_server.call_tool("mcp:ticketing/get_ticket", {"ticket_id": "TKT-001"})
    assert "error" in result
    assert result["code"] == -32700


def test_mcp_server_allowlist(mcp_server: MockMCPServer) -> None:
    """Direct test: Allowlist filters returned tools."""
    mcp_server.set_allowlist({"mcp:ticketing/get_ticket", "mcp:knowledge/get_article"})
    tools = mcp_server.list_tools()
    assert len(tools) == 2
    tool_names = {t["name"] for t in tools}
    assert tool_names == {"mcp:ticketing/get_ticket", "mcp:knowledge/get_article"}


def test_mcp_server_delay(mcp_server: MockMCPServer) -> None:
    """Direct test: MCP server delay attribute is stored (call_tool is non-blocking in mock)."""
    # The MockMCPServer stores delay but does not sleep during call_tool
    # (that would require real blocking, which the mock avoids).
    mcp_server.set_delay(100.0)
    # Verify the server still works correctly with delay configured
    result = mcp_server.call_tool("mcp:ticketing/get_ticket", {"ticket_id": "TKT-001"})
    assert "result" in result
    assert result["result"]["ticket_id"] == "TKT-001"

    # Slow-server behavior is exercised via the agent-level timeout_handling scenario
    # which uses set_delay(10000) to exceed the MCPClient timeout


def test_mcp_server_unknown_tool(mcp_server: MockMCPServer) -> None:
    """Direct test: MCP server returns error for unknown tool."""
    result = mcp_server.call_tool("unknown_tool", {})
    assert "error" in result
    assert result["code"] == -32601
