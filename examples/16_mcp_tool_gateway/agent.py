"""Pattern 16: MCP Tool Gateway.

Scenario: Expose mocked ticketing and knowledge-search tools through a local MCP
(Model Context Protocol) server, consumed by an ADK-style agent. The agent
discovers tools via MCP's tools/list, invokes them via MCP's tools/call, and
returns a final answer.

Demonstrates:
- Tool discovery (list_tools) returning a catalog of available MCP tools
- Tool invocation (call_tool) with typed arguments
- Namespaced tools (mcp:ticketing/*, mcp:knowledge/*)
- Allowlist filtering of exposed tools
- Tool-definition override (modifying input schemas on the client side)
- Timeout handling and malformed-response handling
- Boundary between ADK orchestration and MCP interoperability
"""

from __future__ import annotations

import json
import time
from typing import Any

from pydantic import BaseModel, Field

from adk_patterns.config import Config
from adk_patterns.contracts import (
    ExecutionStatus,
    PatternRunResult,
    ToolInvocationRecord,
)
from adk_patterns.mocks.mcp_server import MCPTool, MockMCPServer
from adk_patterns.models import ScriptedModel, text_response, tool_call_response
from adk_patterns.shared import RunContext, run_scope


# ---------------------------------------------------------------------------
# Typed contracts
# ---------------------------------------------------------------------------


class TicketingCreateTicketParams(BaseModel):
    """Parameters for creating a support ticket."""

    title: str = Field(description="Ticket title")
    description: str = Field(description="Detailed description of the issue")
    priority: str = Field(description="Priority level: low, medium, high, critical")


class TicketingGetTicketParams(BaseModel):
    """Parameters for retrieving a ticket."""

    ticket_id: str = Field(description="Ticket identifier (e.g., TKT-001)")


class TicketingListTicketsParams(BaseModel):
    """Parameters for listing tickets."""

    status: str = Field(default="open", description="Filter by status: open, closed, all")


class KnowledgeSearchDocsParams(BaseModel):
    """Parameters for searching knowledge base documents."""

    query: str = Field(description="Search query string")


class KnowledgeGetArticleParams(BaseModel):
    """Parameters for retrieving a knowledge article."""

    article_id: str = Field(description="Article identifier (e.g., KB-001)")


# ---------------------------------------------------------------------------
# MCP tool handlers
# ---------------------------------------------------------------------------

# Ticketing data
_tickets: dict[str, dict[str, Any]] = {
    "TKT-001": {
        "ticket_id": "TKT-001",
        "title": "Login page returns 500 error",
        "description": "Users cannot log in after the latest deployment.",
        "priority": "critical",
        "status": "open",
        "created_at": "2026-06-18T10:00:00Z",
    },
    "TKT-002": {
        "ticket_id": "TKT-002",
        "title": "Slow query on dashboard",
        "description": "Dashboard takes >30s to load for admin users.",
        "priority": "high",
        "status": "open",
        "created_at": "2026-06-17T14:30:00Z",
    },
}

# Knowledge base data
_knowledge_articles: dict[str, dict[str, Any]] = {
    "KB-001": {
        "article_id": "KB-001",
        "title": "Deployment Rollback Procedure",
        "content": "To roll back a deployment, run `deploy rollback <version>` in the CI pipeline.",
        "tags": ["deployment", "rollback", "operations"],
    },
    "KB-002": {
        "article_id": "KB-002",
        "title": "Common Error Codes",
        "content": "Error 500: Internal server error. Check application logs for stack trace.",
        "tags": ["errors", "troubleshooting", "logs"],
    },
}


def _handle_create_ticket(title: str, description: str, priority: str = "low") -> dict[str, Any]:
    """Create a new support ticket."""
    ticket_id = f"TKT-{len(_tickets) + 1:03d}"
    ticket = {
        "ticket_id": ticket_id,
        "title": title,
        "description": description,
        "priority": priority,
        "status": "open",
        "created_at": "2026-06-19T08:00:00Z",
    }
    _tickets[ticket_id] = ticket
    return ticket


def _handle_get_ticket(ticket_id: str) -> dict[str, Any]:
    """Retrieve a ticket by ID."""
    ticket = _tickets.get(ticket_id)
    if ticket is None:
        return {"error": f"Ticket not found: {ticket_id}", "ticket_id": ticket_id}
    return dict(ticket)


def _handle_list_tickets(status: str = "open") -> dict[str, Any]:
    """List tickets, optionally filtered by status."""
    if status == "all":
        results = list(_tickets.values())
    else:
        results = [t for t in _tickets.values() if t["status"] == status]
    return {"tickets": results, "count": len(results)}


def _handle_search_docs(query: str) -> dict[str, Any]:
    """Search knowledge base articles."""
    q = query.lower()
    results = [
        a for a in _knowledge_articles.values()
        if q in a["title"].lower() or q in a["content"].lower() or any(q in t.lower() for t in a["tags"])
    ]
    return {"results": results, "count": len(results)}


def _handle_get_article(article_id: str) -> dict[str, Any]:
    """Retrieve a knowledge article by ID."""
    article = _knowledge_articles.get(article_id)
    if article is None:
        return {"error": f"Article not found: {article_id}", "article_id": article_id}
    return dict(article)


# ---------------------------------------------------------------------------
# MCP Server setup
# ---------------------------------------------------------------------------


def build_mcp_server() -> MockMCPServer:
    """Build and configure the MCP server with ticketing and knowledge tools."""
    server = MockMCPServer(name="ticketing-knowledge-mcp", version="2.0.0")

    # Register ticketing tools (namespaced as mcp:ticketing/*)
    server.register_tool(
        MCPTool(
            name="mcp:ticketing/create_ticket",
            description="Create a new support ticket with title, description, and priority.",
            input_schema=TicketingCreateTicketParams.model_json_schema(),
            handler=_handle_create_ticket,
            version="1.0.0",
        )
    )
    server.register_tool(
        MCPTool(
            name="mcp:ticketing/get_ticket",
            description="Retrieve a support ticket by its ticket ID.",
            input_schema=TicketingGetTicketParams.model_json_schema(),
            handler=_handle_get_ticket,
            version="1.0.0",
        )
    )
    server.register_tool(
        MCPTool(
            name="mcp:ticketing/list_tickets",
            description="List support tickets, optionally filtered by status.",
            input_schema=TicketingListTicketsParams.model_json_schema(),
            handler=_handle_list_tickets,
            version="1.0.0",
        )
    )

    # Register knowledge tools (namespaced as mcp:knowledge/*)
    server.register_tool(
        MCPTool(
            name="mcp:knowledge/search_docs",
            description="Search knowledge base documents by query string.",
            input_schema=KnowledgeSearchDocsParams.model_json_schema(),
            handler=_handle_search_docs,
            version="1.0.0",
        )
    )
    server.register_tool(
        MCPTool(
            name="mcp:knowledge/get_article",
            description="Retrieve a knowledge base article by article ID.",
            input_schema=KnowledgeGetArticleParams.model_json_schema(),
            handler=_handle_get_article,
            version="1.0.0",
        )
    )

    return server


# ---------------------------------------------------------------------------
# Fixture sequences
# ---------------------------------------------------------------------------

SEQUENCES: dict[str, list] = {
    # --- Tool discovery: model asks to list tools ---------------------------
    "tool_discovery": [
        tool_call_response("list_mcp_tools", {}, call_id="call_disc_1"),
        text_response(
            "The MCP server exposes 5 tools across two namespaces: "
            "mcp:ticketing (create_ticket, get_ticket, list_tickets) "
            "and mcp:knowledge (search_docs, get_article)."
        ),
    ],
    # --- Tool invocation: create a ticket -----------------------------------
    "tool_invocation": [
        tool_call_response(
            "mcp:ticketing/create_ticket",
            {"title": "Test ticket", "description": "This is a test", "priority": "low"},
            call_id="call_tc1",
        ),
        text_response(
            "Successfully created ticket TKT-003 with low priority. "
            "The ticket is now open and ready for triage."
        ),
    ],
    # --- Multi-tool: create ticket + search docs ----------------------------
    "multi_tool": [
        tool_call_response(
            "mcp:ticketing/create_ticket",
            {"title": "Bug report", "description": "Page crash on submit", "priority": "high"},
            call_id="call_mt1",
        ),
        tool_call_response(
            "mcp:knowledge/search_docs",
            {"query": "deployment rollback"},
            call_id="call_mt2",
        ),
        text_response(
            "Created ticket TKT-003 for the page crash issue, "
            "and found knowledge base articles about deployment rollback."
        ),
    ],
    # --- Malformed response from MCP server ---------------------------------
    "malformed_response": [
        tool_call_response("mcp:ticketing/get_ticket", {"ticket_id": "TKT-001"}, call_id="call_mf1"),
        text_response(
            "The MCP server returned a malformed response (error code -32700). "
            "The request could not be processed."
        ),
    ],
    # --- Timeout handling ---------------------------------------------------
    "timeout_handling": [
        tool_call_response("mcp:ticketing/get_ticket", {"ticket_id": "TKT-001"}, call_id="call_to1"),
        text_response(
            "The MCP server timed out while processing the get_ticket request. "
            "Consider retrying or checking server health."
        ),
    ],
    # --- Allowlist filtering ------------------------------------------------
    "allowlist_filtering": [
        tool_call_response("list_mcp_tools", {}, call_id="call_alw_1"),
        text_response(
            "After allowlist filtering, 2 tools are available: "
            "mcp:ticketing/get_ticket, mcp:knowledge/get_article."
        ),
    ],
    # --- Namespaced tools ---------------------------------------------------
    "namespaced_tools": [
        tool_call_response("mcp:knowledge/search_docs", {"query": "error codes"}, call_id="call_ns1"),
        text_response(
            "Searched mcp:knowledge/search_docs for 'error codes'. "
            "Found article KB-002 about common error codes."
        ),
    ],
}

QUERIES: dict[str, str] = {
    "tool_discovery": "List all available MCP tools.",
    "tool_invocation": "Create a low-priority test ticket.",
    "multi_tool": "Create a high-priority bug ticket and search for deployment documentation.",
    "malformed_response": "Get ticket TKT-001 (server will return malformed response).",
    "timeout_handling": "Get ticket TKT-001 (server will simulate timeout).",
    "allowlist_filtering": "List available tools after allowlist filtering.",
    "namespaced_tools": "Search knowledge base for error codes.",
}


# ---------------------------------------------------------------------------
# MCP Client wrapper
# ---------------------------------------------------------------------------


class MCPClient:
    """In-process MCP client that wraps MockMCPServer.

    Demonstrates the boundary between ADK orchestration (this client)
    and MCP interoperability (the server).
    """

    def __init__(self, server: MockMCPServer, timeout_ms: float = 5000.0) -> None:
        self._server = server
        self._timeout_ms = timeout_ms

    def set_timeout(self, timeout_ms: float) -> None:
        self._timeout_ms = timeout_ms

    def list_tools(self) -> list[dict[str, Any]]:
        """Call MCP tools/list and return the tool catalog.

        Raises:
            TimeoutError: If the server takes longer than timeout_ms.
        """
        start = time.monotonic()
        # Simulate potential delay (MCP server may be slow)
        elapsed = (time.monotonic() - start) * 1000
        if elapsed > self._timeout_ms:
            raise TimeoutError(f"MCP list_tools timed out after {self._timeout_ms}ms")
        return self._server.list_tools()

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call MCP tools/call and return the result.

        Simulates server delay when configured on the MockMCPServer.
        Raises TimeoutError if the effective call time exceeds the client timeout.

        Raises:
            TimeoutError: If the server takes longer than timeout_ms.
        """
        # Respect any delay configured on the server (used for timeout testing)
        if hasattr(self._server, '_delay_ms') and self._server._delay_ms > 0:
            delay_s = self._server._delay_ms / 1000.0
            if delay_s * 1000 > self._timeout_ms:
                time.sleep(self._timeout_ms / 1000.0)  # consume the client timeout
                raise TimeoutError(
                    f"MCP call_tool({name}) timed out after {self._timeout_ms}ms "
                    f"(server delay: {self._server._delay_ms}ms)"
                )
            time.sleep(delay_s)

        start = time.monotonic()
        result = self._server.call_tool(name, arguments)
        elapsed = (time.monotonic() - start) * 1000
        if elapsed > self._timeout_ms:
            raise TimeoutError(f"MCP call_tool({name}) timed out after {self._timeout_ms}ms")
        return result


# ---------------------------------------------------------------------------
# Tool definitions (ADK-compatible format)
# ---------------------------------------------------------------------------


def _tool_definitions() -> list[dict[str, Any]]:
    """Return MCP tool definitions in an ADK-compatible format.

    These are client-side tool definitions that the model sees.
    They can be overridden (e.g., simplified descriptions) without
    changing the MCP server itself — demonstrating tool-definition override.
    """
    return [
        {
            "name": "list_mcp_tools",
            "description": "Discover available MCP tools from the server. Returns a list of tool definitions.",
            "parameters": {},
        },
        {
            "name": "mcp:ticketing/create_ticket",
            "description": "Create a new support ticket. CLIENT-OVERRIDE: Uses simplified schema.",
            "parameters": {
                "title": {"type": "string", "description": "Ticket title"},
                "description": {"type": "string", "description": "Issue description"},
                "priority": {"type": "string", "description": "Priority: low, medium, high, critical"},
            },
        },
        {
            "name": "mcp:ticketing/get_ticket",
            "description": "Retrieve a support ticket by ID.",
            "parameters": {"ticket_id": {"type": "string", "description": "Ticket ID (e.g., TKT-001)"}},
        },
        {
            "name": "mcp:ticketing/list_tickets",
            "description": "List support tickets filtered by status.",
            "parameters": {"status": {"type": "string", "description": "Filter: open, closed, all"}},
        },
        {
            "name": "mcp:knowledge/search_docs",
            "description": "Search the knowledge base using a query string.",
            "parameters": {"query": {"type": "string", "description": "Search query"}},
        },
        {
            "name": "mcp:knowledge/get_article",
            "description": "Retrieve a knowledge base article by article ID.",
            "parameters": {"article_id": {"type": "string", "description": "Article ID (e.g., KB-001)"}},
        },
    ]


def _build_server_for_scenario(scenario: str, mcp: MockMCPServer) -> MockMCPServer:
    """Configure the MCP server based on the test scenario.

    This isolates scenario-specific server behavior (malformed, timeout, allowlist).
    """
    mcp.reset()

    # Re-register tools (reset clears them)
    mcp.register_tool(
        MCPTool(name="mcp:ticketing/create_ticket", description="Create a support ticket.",
                input_schema=TicketingCreateTicketParams.model_json_schema(),
                handler=_handle_create_ticket)
    )
    mcp.register_tool(
        MCPTool(name="mcp:ticketing/get_ticket", description="Get ticket details.",
                input_schema=TicketingGetTicketParams.model_json_schema(),
                handler=_handle_get_ticket)
    )
    mcp.register_tool(
        MCPTool(name="mcp:ticketing/list_tickets", description="List tickets by status.",
                input_schema=TicketingListTicketsParams.model_json_schema(),
                handler=_handle_list_tickets)
    )
    mcp.register_tool(
        MCPTool(name="mcp:knowledge/search_docs", description="Search knowledge base.",
                input_schema=KnowledgeSearchDocsParams.model_json_schema(),
                handler=_handle_search_docs)
    )
    mcp.register_tool(
        MCPTool(name="mcp:knowledge/get_article", description="Get knowledge article.",
                input_schema=KnowledgeGetArticleParams.model_json_schema(),
                handler=_handle_get_article)
    )

    if scenario == "malformed_response":
        mcp.set_malformed()

    if scenario == "timeout_handling":
        mcp.set_delay(10_000.0)  # 10 second delay to simulate timeout

    if scenario == "allowlist_filtering":
        mcp.set_allowlist({"mcp:ticketing/get_ticket", "mcp:knowledge/get_article"})

    return mcp


# ---------------------------------------------------------------------------
# Core orchestration
# ---------------------------------------------------------------------------


def run_mcp_gateway(
    ctx: RunContext,
    model: ScriptedModel,
    mcp_client: MCPClient,
    query: str,
) -> dict[str, Any]:
    """Run the MCP Tool Gateway orchestration loop.

    The ADK-style agent discovers tools from the MCP server via list_tools,
    invokes them via call_tool, and synthesizes a final answer.

    State keys:
        mcp_tools[] — The full tool catalog from MCP tools/list
        mcp_results{} — Results of tool invocations keyed by tool name
        final_answer — The model's final response text

    Args:
        ctx: Run context for audit and budget tracking.
        model: ScriptedModel with pre-configured response sequence.
        mcp_client: Client wrapping the MockMCPServer.
        query: The user's request text.

    Returns:
        A dict with keys: mcp_tools, mcp_results, final_answer.
    """
    state: dict[str, Any] = {
        "mcp_tools": [],
        "mcp_results": {},
        "final_answer": "",
    }
    messages: list[dict[str, Any]] = [{"role": "user", "content": query}]

    system_prompt = (
        "You are an MCP Tool Gateway agent. You have access to tools provided by an "
        "MCP server through a client interface.\n\n"
        "Available client-side tools:\n"
        "- list_mcp_tools() — Discover all available MCP tools from the server.\n"
        "- mcp:ticketing/create_ticket(title, description, priority) — Create a support ticket.\n"
        "- mcp:ticketing/get_ticket(ticket_id) — Get ticket details.\n"
        "- mcp:ticketing/list_tickets(status) — List tickets by status.\n"
        "- mcp:knowledge/search_docs(query) — Search the knowledge base.\n"
        "- mcp:knowledge/get_article(article_id) — Get an article.\n\n"
        "Call tools one at a time. When you have the information you need, "
        "provide a clear final answer. Tool names use the mcp:namespace/name convention."
    )

    for iteration in range(3):  # bounded iteration budget
        ctx.record_iteration()

        budget_status = ctx.check_budget()
        if budget_status is not None:
            state["final_answer"] = "Budget exhausted before completing the request."
            ctx.mark_budget_exhausted()
            break

        response = model.invoke(
            system_instruction=system_prompt,
            messages=messages,
            tools=_tool_definitions(),
        )
        ctx.record_model_call(tokens=response.usage.total_tokens)
        ctx.audit("agent", "model_call", resource=f"iteration_{iteration}")

        # Process tool calls
        if response.tool_calls:
            for tc in response.tool_calls:
                ctx.audit("agent", "tool_call", resource=tc.name, metadata={"call_id": tc.id})

                if tc.name == "list_mcp_tools":
                    # Special client-side tool: discover MCP tools
                    try:
                        tools = mcp_client.list_tools()
                        state["mcp_tools"] = tools
                        result_text = f"MCP tools discovered ({len(tools)} tools): {[t['name'] for t in tools]}"
                    except TimeoutError as e:
                        result_text = f"MCP tool discovery timed out: {e}"
                        ctx.audit("agent", "tool_error", resource="list_mcp_tools",
                                  outcome="timeout", metadata={"error": str(e)})
                else:
                    # MCP tool invocation via call_tool
                    try:
                        result = mcp_client.call_tool(tc.name, tc.arguments)
                        ctx.record_tool_call(
                            ToolInvocationRecord(
                                tool_name=tc.name,
                                validated_arguments=dict(tc.arguments),
                                result_summary={"status": "success" if "result" in result else "error"},
                            )
                        )
                        state["mcp_results"][tc.name] = result
                        result_text = f"MCP tool {tc.name} returned: {result}"
                    except TimeoutError as e:
                        ctx.record_tool_call(
                            ToolInvocationRecord(
                                tool_name=tc.name,
                                validated_arguments=dict(tc.arguments),
                                error_type="TimeoutError",
                            )
                        )
                        ctx.audit("agent", "tool_error", resource=tc.name,
                                  outcome="timeout", metadata={"error": str(e)})
                        state["mcp_results"][tc.name] = {"error": str(e), "error_type": "TimeoutError"}
                        result_text = f"MCP tool {tc.name} timed out: {e}"

                messages.append({"role": "user", "content": result_text})
        else:
            # Text response from model — this is the final answer
            state["final_answer"] = response.text
            ctx.audit("agent", "final_answer", outcome="success", metadata={"answer": response.text})
            break

    ctx.snapshot_state(state)
    return state


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def run(config: Config | None = None, scenario: str = "default") -> PatternRunResult:
    """Entry point for CLI and tests.

    Args:
        config: Application configuration (uses defaults if None).
        scenario: Test scenario key.

    Returns:
        A PatternRunResult with status, output, metrics, and audit trail.
    """
    model = ScriptedModel()

    seq = SEQUENCES.get(scenario)
    if seq:
        model.set_response_sequence(seq)

    query = QUERIES.get(scenario, "List available MCP tools and create a ticket.")

    mcp_server = MockMCPServer(name="ticketing-knowledge-mcp", version="2.0.0")
    mcp_server = _build_server_for_scenario(scenario, mcp_server)
    mcp_client = MCPClient(mcp_server, timeout_ms=5000.0)

    with run_scope(
        "mcp-tool-gateway",
        scenario,
        max_model_calls=3,
        max_tool_calls=5,
    ) as ctx:
        state = run_mcp_gateway(ctx, model, mcp_client, query)
        ctx.output = state

    return ctx.to_result()


def main(config: Config | None = None, scenario: str = "default") -> PatternRunResult:
    """Standard entry point called by CLI."""
    return run(config=config, scenario=scenario)
