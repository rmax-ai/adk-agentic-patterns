# Pattern 16: MCP Tool Gateway

**Phase:** 4 — Tool-Aware Agents  
**Autonomy Level:** 5/10 (agent selects MCP tools; MCP protocol is deterministic)  

---

## Overview

The **MCP Tool Gateway** pattern exposes tools from an MCP (Model Context Protocol) server through an ADK-style agent orchestration layer. Instead of hard-coding tool functions into the agent, the agent discovers and invokes tools dynamically via the MCP protocol — the same protocol used by real-world MCP servers (file systems, databases, APIs).

This pattern demonstrates how to bridge two worlds:
- **ADK orchestration** — manages agent state, model calls, tool execution loop, budgets, and auditing
- **MCP interoperability** — provides a standardized protocol for tool discovery (`tools/list`) and invocation (`tools/call`)

### What makes this different from Pattern 04 (Tool-Using Agent)?

Pattern 04 directly imports Python functions as tools. The MCP Tool Gateway inserts a protocol boundary: the agent talks to an MCP server through `list_tools` and `call_tool`, just as it would with a remote MCP service. This enables:
- Dynamic tool discovery at runtime (no hard-coded tool registry)
- Namespaced tool names (`mcp:ticketing/*`, `mcp:knowledge/*`)
- Allowlist-based access control
- Tool-definition overrides on the client side
- Protocol-level error handling (malformed responses, timeouts)

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│  ADK Orchestration Layer                        │
│                                                  │
│  ┌──────────┐   model.invoke()    ┌───────────┐ │
│  │          │◄────────────────────│           │ │
│  │  Agent   │                     │  Model    │ │
│  │  Loop    │────────────────────►│ (Scripted)│ │
│  │          │   tool_calls        │           │ │
│  └────┬─────┘                     └───────────┘ │
│       │                                          │
│       │  MCP Client wrapper                      │
│       │  ┌──────────────────┐                    │
│       └──►  list_tools()    │                    │
│          │  call_tool()     │                    │
│          └──────┬───────────┘                    │
└─────────────────┼───────────────────────────────┘
                  │  MCP Protocol
┌─────────────────┼───────────────────────────────┐
│  MCP Server     ▼                                │
│  (MockMCPServer)                                 │
│                                                  │
│  ┌────────────────────────────────────┐          │
│  │  Registered Tools                  │          │
│  │  ┌──────────────────────────┐      │          │
│  │  │ mcp:ticketing/           │      │          │
│  │  │  ├── create_ticket       │      │          │
│  │  │  ├── get_ticket          │      │          │
│  │  │  └── list_tickets        │      │          │
│  │  ├──────────────────────────┤      │          │
│  │  │ mcp:knowledge/           │      │          │
│  │  │  ├── search_docs         │      │          │
│  │  │  └── get_article         │      │          │
│  │  └──────────────────────────┘      │          │
│  └────────────────────────────────────┘          │
└──────────────────────────────────────────────────┘
```

---

## State Keys

| Key | Type | Description |
|-----|------|-------------|
| `mcp_tools[]` | `list[dict]` | Full tool catalog from MCP `tools/list` |
| `mcp_results{}` | `dict[str, Any]` | Results of tool invocations, keyed by tool name |
| `final_answer` | `str` | The model's synthesized response to the user |

---

## Budget

| Resource | Limit |
|----------|-------|
| `max_model_calls` | 3 |
| `max_tool_calls` | 5 |

---

## Scenarios

| Scenario | Description | Model Calls | Tool Calls |
|----------|-------------|-------------|------------|
| `tool_discovery` | Model discovers all 5 MCP tools via `list_mcp_tools` | 2 | 1 |
| `tool_invocation` | Model creates a support ticket | 2 | 1 |
| `multi_tool` | Model calls ticketing + knowledge tools | 3 | 2 |
| `malformed_response` | MCP server returns bad JSON (code -32700) | 2 | 1 |
| `timeout_handling` | MCP server delays beyond timeout | 2 | 1 |
| `allowlist_filtering` | Only 2 allowlisted tools exposed | 2 | 1 |
| `namespaced_tools` | Knowledge search with namespaced tool name | 2 | 1 |

---

## Tests

```bash
# Run all MCP Tool Gateway tests
pytest examples/16_mcp_tool_gateway/test_example.py -v

# Run individual test
pytest examples/16_mcp_tool_gateway/test_example.py::test_tool_discovery -v
pytest examples/16_mcp_tool_gateway/test_example.py::test_mcp_server_list_tools -v
```

### Test Descriptions

| Test | What it verifies |
|------|-----------------|
| `test_tool_discovery` | `list_tools` returns all 5 namespaced MCP tools in catalog |
| `test_tool_invocation` | `call_tool` creates a ticket and returns structured result |
| `test_multi_tool_invocation` | Multiple tools from different namespaces invoked in sequence |
| `test_malformed_response` | Server error code -32700 handled without agent crash |
| `test_timeout_handling` | Server delay triggers client-side timeout; agent continues |
| `test_allowlist_filtering` | Only allowlisted tools appear in `list_tools` output |
| `test_namespaced_tools` | `mcp:knowledge/` tools invoked and results returned |
| `test_audit_trail` | Every MCP call recorded with namespaced resource names |
| `test_mcp_server_list_tools` | (Direct) All 5 tools registered with correct names |
| `test_mcp_server_call_ticketing` | (Direct) Ticketing tool handler works correctly |
| `test_mcp_server_call_knowledge` | (Direct) Knowledge search returns matching articles |
| `test_mcp_server_malformed_flag` | (Direct) Malformed flag returns error code -32700 |
| `test_mcp_server_allowlist` | (Direct) Allowlist limits returned tool count to 2 |
| `test_mcp_server_delay` | (Direct) Delay simulation works as expected |
| `test_mcp_server_unknown_tool` | (Direct) Unknown tool returns code -32601 |

---

## Key Concepts

### 1. MCP Protocol Boundary

The `MCPClient` class wraps `MockMCPServer` and provides two methods:

```python
class MCPClient:
    def list_tools(self) -> list[dict]: ...
    def call_tool(self, name: str, arguments: dict) -> dict: ...
```

This mirrors the real MCP protocol (`tools/list`, `tools/call`) and creates a clean boundary. The agent never accesses the server internals directly — only through the protocol.

### 2. Tool Namespacing

Tools are registered with namespaced names following the convention `mcp:<domain>/<name>`:

- `mcp:ticketing/create_ticket`
- `mcp:ticketing/get_ticket`
- `mcp:ticketing/list_tickets`
- `mcp:knowledge/search_docs`
- `mcp:knowledge/get_article`

The namespace is part of the tool name, not a separate field. This prevents name collisions between domains and makes the tool's origin visible in audit logs.

### 3. Allowlist Filtering

The MCP server supports an allowlist (`set_allowlist`) that filters which tools are returned by `list_tools` and accessible via `call_tool`. This allows the agent to restrict which tools the model can discover and use.

```python
server.set_allowlist({"mcp:ticketing/get_ticket", "mcp:knowledge/get_article"})
# list_tools() now only returns these 2 tools
```

### 4. Tool-Definition Override

The client-side tool definitions (`_tool_definitions()`) can differ from the server-side input schemas. This allows the agent to present simplified or modified tool descriptions to the model without changing the MCP server:

```python
# Server-side schema: full Pydantic schema
MCPTool(input_schema=TicketingCreateTicketParams.model_json_schema())

# Client-side override: simplified flat dict
{
    "name": "mcp:ticketing/create_ticket",
    "parameters": {
        "title": {"type": "string"},
        "priority": {"type": "string"},
    },
}
```

### 5. Error Handling

Two categories of errors are demonstrated:

**Protocol errors** (returned by `call_tool`):
- Server returns `{"error": "...", "code": -32700}` for malformed requests
- Server returns `{"error": "...", "code": -32601}` for unknown tools

**Client errors** (raised by `MCPClient`):
- `TimeoutError` when server exceeds configured timeout
- Network-level errors (in real deployments)

Both are surfaced in `mcp_results[]` and audit events, allowing the agent to continue gracefully.

---

## Running

```bash
# Run the default scenario (tool_discovery)
python examples/16_mcp_tool_gateway/run.py

# Run a specific scenario
python examples/16_mcp_tool_gateway/run.py --scenario tool_invocation
python examples/16_mcp_tool_gateway/run.py --scenario allowlist_filtering
```

---

## Dependencies

- `MockMCPServer` from `adk_patterns.mocks.mcp_server` (in-process MCP server)
- `MCPTool` dataclass for tool registration
- `ScriptedModel` with response sequences for deterministic testing
- No remote network dependencies — everything runs in-process

---

## Comparison with Pattern 04 (Tool-Using Agent)

| Aspect | Pattern 04 | Pattern 16 (this) |
|--------|-----------|-------------------|
| Tool source | Hard-coded Python functions | MCP server (protocol-based) |
| Tool discovery | Static registry | Dynamic `tools/list` |
| Tool names | Flat (e.g., `get_order_status`) | Namespaced (`mcp:ticketing/`) |
| Protocol boundary | None | Explicit `MCPClient` wrapper |
| Tool definition override | N/A | Client can override server schemas |
| Error model | Python exceptions | Protocol codes + client exceptions |
| Allowlist | N/A | Server-side allowlist |
