"""Pattern 04: Tool-Using Agent.

Scenario: Inspect an order and answer its status using mocked inventory,
shipment, and customer systems.

Demonstrates:
- ADK-style tools (FunctionTool / callable functions with typed arguments)
- Tool descriptions designed for reliable selection
- Invalid argument type detection
- Unavailable tool error handling
- Full audit trail via RunContext
- Read-only tools — no write operations
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from adk_patterns.config import Config
from adk_patterns.contracts import (
    ExecutionStatus,
    PatternRunResult,
    ToolInvocationRecord,
)
from adk_patterns.mocks.inventory_service import MockInventoryService, OrderStatus
from adk_patterns.models import ScriptedModel, text_response, tool_call_response
from adk_patterns.shared import RunContext, run_scope

# ---------------------------------------------------------------------------
# Typed contracts
# ---------------------------------------------------------------------------


class OrderStatusRequest(BaseModel):
    """Request to look up an order's current status."""

    order_id: str = Field(description="Order identifier (e.g., ORD-001)")


class OrderItem(BaseModel):
    """A single line item on an order."""

    item_id: str
    name: str
    quantity: int
    price: float


class OrderStatusResult(BaseModel):
    """Full order status including items and customer reference."""

    order_id: str
    status: str
    customer_id: str
    items: list[OrderItem] = Field(default_factory=list)


class ShipmentStatusRequest(BaseModel):
    """Request to look up a shipment by tracking number."""

    tracking_id: str = Field(description="Tracking identifier (e.g., TRK-999)")


class ShipmentStatusResult(BaseModel):
    """Current shipment tracking information."""

    tracking_id: str
    status: str
    estimated_delivery: str | None = None


class CustomerInfoRequest(BaseModel):
    """Request for customer profile information."""

    customer_id: str = Field(description="Customer identifier (e.g., CUST-042)")


class CustomerInfoResult(BaseModel):
    """Customer profile data."""

    customer_id: str
    name: str
    email: str


# ---------------------------------------------------------------------------
# Fixtures
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

QUERIES: dict[str, str] = {
    "order_status": "Check the status of order ORD-001.",
    "multi_tool": "Look up order ORD-001 and tell me about the customer.",
    "invalid_arg": "Check the status of my order.",
    "unavailable_tool": "Use the magic_tool to inspect order ORD-001.",
}

# ---------------------------------------------------------------------------
# Shared mock services (read-only, shared across all tool calls)
# ---------------------------------------------------------------------------

_inventory = MockInventoryService()
_shipment_data: dict[str, dict[str, Any]] = {
    "TRK-999": {"tracking_id": "TRK-999", "status": "in_transit", "estimated_delivery": "2026-06-20"},
    "TRK-888": {"tracking_id": "TRK-888", "status": "delivered", "estimated_delivery": "2026-06-15"},
}
_customer_data: dict[str, dict[str, Any]] = {
    "CUST-042": {"customer_id": "CUST-042", "name": "Alice Smith", "email": "alice@example.com"},
    "CUST-007": {"customer_id": "CUST-007", "name": "Bob Jones", "email": "bob@example.com"},
}

# Seed inventory with test data
_inventory.create_order("ORD-001", "CUST-042", [])
_inventory._orders["ORD-001"].status = OrderStatus.SHIPPED
_inventory._orders["ORD-001"].metadata = {
    "items": [
        {"item_id": "ITM-001", "name": "Widget A", "quantity": 2, "price": 19.99},
        {"item_id": "ITM-002", "name": "Gadget B", "quantity": 1, "price": 49.99},
    ]
}
_inventory.create_order("ORD-002", "CUST-007", [])
_inventory._orders["ORD-002"].status = OrderStatus.DELIVERED


# ---------------------------------------------------------------------------
# Tool implementations (read-only)
# ---------------------------------------------------------------------------


def get_order_status(order_id: str) -> dict[str, Any]:
    """Look up an order by its ID and return current status details.

    Args:
        order_id: The order identifier to look up (e.g., ORD-001).

    Returns:
        A dict with order_id, status, customer_id, and items.
    """
    order = _inventory.get_order(order_id)
    if order is None:
        return {"order_id": order_id, "status": "not_found", "customer_id": "", "items": []}
    return {
        "order_id": order.order_id,
        "status": order.status.value,
        "customer_id": order.customer_id,
        "items": [
            {"item_id": it.item_id, "name": it.name, "quantity": it.quantity, "price": it.price}
            for it in order.items
        ]
        or order.metadata.get("items", []),
    }


def get_shipment_status(tracking_id: str) -> dict[str, Any]:
    """Look up a shipment by its tracking number.

    Args:
        tracking_id: The tracking number to look up (e.g., TRK-999).

    Returns:
        A dict with tracking_id, status, and estimated_delivery.
    """
    record = _shipment_data.get(tracking_id)
    if record is None:
        return {"tracking_id": tracking_id, "status": "not_found", "estimated_delivery": None}
    return dict(record)


def get_customer_info(customer_id: str) -> dict[str, Any]:
    """Retrieve customer profile information.

    Args:
        customer_id: The customer identifier (e.g., CUST-042).

    Returns:
        A dict with customer_id, name, and email.
    """
    record = _customer_data.get(customer_id)
    if record is None:
        return {"customer_id": customer_id, "name": "unknown", "email": ""}
    return dict(record)


# -- Tool registry -----------------------------------------------------------

TOOL_REGISTRY: dict[str, Any] = {
    "get_order_status": get_order_status,
    "get_shipment_status": get_shipment_status,
    "get_customer_info": get_customer_info,
}


def _tool_definitions() -> list[dict[str, Any]]:
    """Return tool definitions in an ADK-compatible format."""
    return [
        {
            "name": "get_order_status",
            "description": "Look up an order by ID. Returns status, customer, and items.",
            "parameters": {"order_id": {"type": "string", "description": "Order ID (e.g., ORD-001)"}},
        },
        {
            "name": "get_shipment_status",
            "description": "Look up a shipment by tracking number. Returns status and delivery ETA.",
            "parameters": {"tracking_id": {"type": "string", "description": "Tracking number (e.g., TRK-999)"}},
        },
        {
            "name": "get_customer_info",
            "description": "Retrieve customer profile by customer ID. Returns name and email.",
            "parameters": {"customer_id": {"type": "string", "description": "Customer ID (e.g., CUST-042)"}},
        },
    ]


# ---------------------------------------------------------------------------
# Core orchestration
# ---------------------------------------------------------------------------


def _validate_and_execute(tool_name: str, arguments: dict[str, Any]) -> Any:
    """Execute a tool with runtime type validation.

    Raises:
        ValueError: If the tool is unknown.
        TypeError: If any argument has the wrong type.
    """
    if tool_name not in TOOL_REGISTRY:
        msg = f"Tool '{tool_name}' is not available. Available tools: {', '.join(sorted(TOOL_REGISTRY))}"
        raise ValueError(msg)

    fn = TOOL_REGISTRY[tool_name]

    # Type validation: ensure string parameters are actually strings
    import inspect
    import typing

    sig = inspect.signature(fn)
    try:
        hints = typing.get_type_hints(fn)
    except Exception:
        hints = {}
    for param_name, param in sig.parameters.items():
        if param_name in arguments:
            actual_value = arguments[param_name]
            expected_type = hints.get(param_name, param.annotation)
            # get_type_hints resolves string annotations to actual types
            if expected_type is str and not isinstance(actual_value, str):
                raise TypeError(
                    f"Argument '{param_name}' must be str, "
                    f"got {type(actual_value).__name__} ({actual_value!r})"
                )

    return fn(**arguments)


def _execute_tool_calls(
    ctx: RunContext,
    tool_calls: list,
) -> dict[str, Any]:
    """Execute a batch of tool calls and record results.

    Returns a dict mapping tool names to their results or error info.
    """
    results: dict[str, Any] = {}

    for tc in tool_calls:
        ctx.audit("agent", "tool_call", resource=tc.name, metadata={"call_id": tc.id})
        try:
            result = _validate_and_execute(tc.name, tc.arguments)
            ctx.record_tool_call(
                ToolInvocationRecord(
                    tool_name=tc.name,
                    validated_arguments=dict(tc.arguments),
                    result_summary={"status": "success"},
                )
            )
            results[tc.name] = result
        except (ValueError, TypeError, Exception) as e:
            error_type = type(e).__name__
            ctx.record_tool_call(
                ToolInvocationRecord(
                    tool_name=tc.name,
                    validated_arguments=dict(tc.arguments),
                    error_type=error_type,
                )
            )
            ctx.audit("agent", "tool_error", resource=tc.name, outcome="failure", metadata={"error": str(e)})
            results[tc.name] = {"error": str(e), "error_type": error_type}

    return results


def run_tool_agent(
    ctx: RunContext,
    model: ScriptedModel,
    query: str,
) -> dict[str, Any]:
    """Run the tool-using agent loop.

    Args:
        ctx: Run context for audit and budget tracking.
        model: ScriptedModel with pre-configured response sequence.
        query: The user's request text.

    Returns:
        A dict with keys 'tool_results' and 'final_answer'.
    """
    state: dict[str, Any] = {"tool_results": {}, "final_answer": ""}
    messages: list[dict[str, Any]] = [{"role": "user", "content": query}]

    system_prompt = (
        "You are an order inspection assistant. You have access to tools that can look up "
        "orders, shipments, and customer information. Use the appropriate tool(s) to answer "
        "the user's question, then provide a clear summary.\n\n"
        "Available tools:\n"
        "- get_order_status(order_id: str) — Look up an order's current status.\n"
        "- get_shipment_status(tracking_id: str) — Look up a shipment's tracking info.\n"
        "- get_customer_info(customer_id: str) — Retrieve customer profile details.\n\n"
        "Call one tool at a time and wait for the result before calling another.\n"
        "When you have all the information you need, provide the final answer."
    )

    for iteration in range(3):  # bounded iteration budget
        ctx.record_iteration()

        response = model.invoke(
            system_instruction=system_prompt,
            messages=messages,
            tools=_tool_definitions(),
        )
        ctx.record_model_call(tokens=response.usage.total_tokens)
        ctx.audit("agent", "model_call", resource=f"iteration_{iteration}")

        # Check if response has tool calls
        if response.tool_calls:
            tool_results = _execute_tool_calls(ctx, response.tool_calls)
            state["tool_results"].update(tool_results)

            # Feed results back to model
            result_lines = []
            for tool_name, result in tool_results.items():
                if "error" in result:
                    result_lines.append(f"Tool {tool_name} returned error: {result['error']}")
                else:
                    result_lines.append(f"Tool {tool_name} returned: {result}")
            messages.append({"role": "user", "content": "\n".join(result_lines)})
        else:
            # Model produced a text response — this is the final answer
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
        scenario: Test scenario key (order_status, multi_tool, invalid_arg, unavailable_tool).

    Returns:
        A PatternRunResult with status, output, metrics, and audit trail.
    """
    model = ScriptedModel()

    seq = SEQUENCES.get(scenario)
    if seq:
        model.set_response_sequence(seq)

    query = QUERIES.get(scenario, "Check the status of order ORD-001.")

    with run_scope("tool-using-agent", scenario, max_model_calls=3, max_tool_calls=5) as ctx:
        state = run_tool_agent(ctx, model, query)
        ctx.output = state

    return ctx.to_result()


def main(config: Config | None = None, scenario: str = "default") -> PatternRunResult:
    """Standard entry point called by CLI."""
    return run(config=config, scenario=scenario)
