# Pattern 04: Tool-Using Agent

**Phase:** 1 · **Autonomy:** Low (2/10) · **Determinism:** High (9/10)

## Scenario

Inspect an order and answer its status using mocked inventory, shipment, and
customer systems. The model selects and calls the appropriate tools based on
tool descriptions, then synthesises the results into a final answer.

## Tools

| Tool | Signature | Description |
|------|-----------|-------------|
| `get_order_status` | `order_id: str → dict` | Look up an order's current status, items, and customer reference |
| `get_shipment_status` | `tracking_id: str → dict` | Look up a shipment's tracking status and delivery ETA |
| `get_customer_info` | `customer_id: str → dict` | Retrieve customer profile (name, email) |

All tools are **read-only** — they never write to any backing store.

## What it demonstrates

- **Tool selection** — the model chooses which tool to call based on its
  description and the user's request
- **Typed arguments** — tool inputs are validated at runtime; mismatched types
  are caught and reported
- **Sequential tool calls** — the model can chain multiple tools to gather
  all the information needed to answer a question
- **Error handling** — when the model requests a non-existent tool or passes an
  invalid argument type, the runtime catches the error and the agent responds
  gracefully
- **Audit trail** — every tool invocation is recorded via `RunContext`,
  including validated arguments, results, and error types
- **Budget enforcement** — bounded execution with `max_model_calls=3` and
  `max_tool_calls=5`

## Test scenarios

| Scenario | Description |
|----------|-------------|
| `order_status` | Single tool call: look up order ORD-001 |
| `multi_tool` | Two tools in sequence: order status + customer info |
| `invalid_arg` | Model passes `int` instead of `str` for `order_id` |
| `unavailable_tool` | Model requests `non_existent_tool` |

## Running

```bash
# Run the default scenario (order_status)
uv run python -m examples.04_tool_using_agent.run

# Run a specific scenario
uv run python -m examples.04_tool_using_agent.run multi_tool

# Run all tests
cd /home/rmax-10/src/adk-agentic-patterns && uv run pytest examples/04_tool_using_agent/ -v
```

## Expected output

```json
{
  "status": "succeeded",
  "output": {
    "tool_results": {
      "get_order_status": {
        "order_id": "ORD-001",
        "status": "shipped",
        "customer_id": "CUST-042",
        "items": [...]
      }
    },
    "final_answer": "Order ORD-001 is in 'shipped' status..."
  },
  "metrics": {
    "model_calls": 2,
    "tool_calls": 1,
    "iterations": 2
  }
}
```
