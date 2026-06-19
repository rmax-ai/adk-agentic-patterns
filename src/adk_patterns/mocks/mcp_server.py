"""Minimal local mock MCP server for the MCP Tool Gateway pattern.

Implements enough of the MCP protocol (JSON-RPC based tool discovery and invocation)
to run entirely in-process without any remote dependency.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class MCPTool:
    """Definition of an MCP tool."""

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"
    handler: Callable[..., Any] | None = None


class MockMCPServer:
    """Minimal in-process MCP server for offline testing.

    Supports tool discovery, invocation, JSON-RPC contracts, malformed request
    handling, delayed responses, permission denial, and tool version metadata.

    Runs entirely in-process — no network, no remote dependency.
    """

    def __init__(self, name: str = "mock-mcp-server", version: str = "1.0.0") -> None:
        self.name = name
        self.version = version
        self._tools: dict[str, MCPTool] = {}
        self._allowlist: set[str] | None = None
        self._delay_ms: float = 0.0
        self._malformed: bool = False
        self._permission_denied: set[str] = set()

    def register_tool(self, tool: MCPTool) -> None:
        self._tools[tool.name] = tool

    def set_allowlist(self, tools: set[str]) -> None:
        self._allowlist = tools

    def set_delay(self, ms: float) -> None:
        self._delay_ms = ms

    def set_malformed(self) -> None:
        self._malformed = True

    def deny_permission(self, tool_name: str) -> None:
        self._permission_denied.add(tool_name)

    # -- MCP protocol methods --

    def list_tools(self) -> list[dict[str, Any]]:
        """MCP tools/list — return available tool definitions."""
        tools = []
        for name, tool in self._tools.items():
            if self._allowlist is not None and name not in self._allowlist:
                continue
            tools.append({
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
                "version": tool.version,
            })
        return tools

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """MCP tools/call — invoke a tool with arguments."""
        if self._malformed:
            self._malformed = False
            return {"error": "Malformed request", "code": -32700}

        if name in self._permission_denied:
            return {"error": f"Permission denied for tool: {name}", "code": -32001}

        if name not in self._tools:
            return {"error": f"Tool not found: {name}", "code": -32601}

        tool = self._tools[name]
        if tool.handler is None:
            return {"error": f"Tool has no handler: {name}", "code": -32603}

        try:
            result = tool.handler(**arguments) if arguments else tool.handler()
            return {"result": result, "id": uuid.uuid4().hex[:8]}
        except Exception as e:
            return {"error": str(e), "code": -32603}

    def handle_request(self, request_json: str) -> str:
        """Handle a JSON-RPC style request."""
        try:
            request = json.loads(request_json)
        except json.JSONDecodeError:
            return json.dumps({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None})

        method = request.get("method", "")
        req_id = request.get("id")

        if method == "tools/list":
            result = self.list_tools()
            return json.dumps({"jsonrpc": "2.0", "result": result, "id": req_id})

        elif method == "tools/call":
            params = request.get("params", {})
            result = self.call_tool(params.get("name", ""), params.get("arguments", {}))
            if "error" in result:
                return json.dumps({"jsonrpc": "2.0", "error": result, "id": req_id})
            return json.dumps({"jsonrpc": "2.0", "result": result["result"], "id": req_id})

        return json.dumps({"jsonrpc": "2.0", "error": {"code": -32601, "message": f"Unknown method: {method}"}, "id": req_id})

    def reset(self) -> None:
        self._tools.clear()
        self._allowlist = None
        self._delay_ms = 0.0
        self._malformed = False
        self._permission_denied.clear()
