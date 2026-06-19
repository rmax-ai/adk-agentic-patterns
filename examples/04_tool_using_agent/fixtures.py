"""ModelResponse fixtures for Pattern 04: Tool-Using Agent.

Each scenario maps to a list of ModelResponse objects that are replayed
in sequence via ScriptedModel.set_response_sequence().

Fixtures cover:
- Single tool call (order status lookup)
- Multi-tool sequence (order → customer)
- Invalid argument type (wrong type passed to tool)
- Unavailable tool (non-existent tool requested)
"""

from __future__ import annotations

from adk_patterns.models import text_response, tool_call_response

# ---------------------------------------------------------------------------
# Scenario response sequences
# Each entry is (scenario_key, list_of_ModelResponse)
# ---------------------------------------------------------------------------

SEQUENCES: dict[str, list] = {
    # --- Happy path: single tool call ---------------------------------------
    "order_status": [
        tool_call_response("get_order_status", {"order_id": "ORD-001"}),
        text_response(
            "Order ORD-001 is in 'shipped' status. "
            "It contains 2 items and was confirmed on 2026-06-10."
        ),
    ],
    # --- Multi-tool: order status + customer info ---------------------------
    "multi_tool": [
        tool_call_response(
            "get_order_status",
            {"order_id": "ORD-001"},
            call_id="call_oc1",
        ),
        tool_call_response(
            "get_customer_info",
            {"customer_id": "CUST-042"},
            call_id="call_cc1",
        ),
        text_response(
            "Order ORD-001 is shipped. Customer: Alice Smith (alice@example.com). "
            "Estimated delivery: 2026-06-18."
        ),
    ],
    # --- Invalid tool argument (int instead of str) --------------------------
    "invalid_arg": [
        tool_call_response(
            "get_order_status",
            {"order_id": 123},  # wrong type — should be str
        ),
        text_response(
            "Error: Argument 'order_id' must be a string, got int. "
            "Please provide a valid order ID."
        ),
    ],
    # --- Unavailable tool called by the model --------------------------------
    "unavailable_tool": [
        tool_call_response(
            "non_existent_tool",
            {"foo": "bar"},
        ),
        text_response(
            "Error: Tool 'non_existent_tool' is not available. "
            "Available tools: get_order_status, get_shipment_status, get_customer_info."
        ),
    ],
}

# ---------------------------------------------------------------------------
# User queries for each scenario
# ---------------------------------------------------------------------------

QUERIES: dict[str, str] = {
    "order_status": "Check the status of order ORD-001.",
    "multi_tool": "Look up order ORD-001 and tell me about the customer.",
    "invalid_arg": "Check the status of my order.",
    "unavailable_tool": "Use the magic_tool to inspect order ORD-001.",
}
