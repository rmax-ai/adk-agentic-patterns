# Pattern 05: ReAct Loop

**Phase:** 2 · **Autonomy:** Medium (5/10) · **Determinism:** Medium (6/10)

## Scenario

Diagnose a fictional service incident by querying metrics, logs, and deployment
history tools. The model dynamically selects read-only tools to gather evidence,
then submits a final diagnosis using the termination tool.

## Tools

| Tool | Signature | Description |
|------|-----------|-------------|
| `query_metrics` | `service: str, metric: str → dict` | Query a service metric value (cpu, memory, error rate, latency) |
| `query_logs` | `service: str, timeframe: str → dict` | Query recent log entries with error count |
| `get_deployment_history` | `service: str → dict` | Get version history and recent changes |
| `submit_diagnosis` | `diagnosis: str, root_cause: str → dict` | **Termination tool** — submit final diagnosis and end the loop |

All tools are **read-only** except `submit_diagnosis`, which only records
the diagnosis without mutating any external service state.

## What it demonstrates

- **ReAct loop** — the model iteratively reasons, acts (calls tools), and
  observes results in a cycle
- **Dynamic tool selection** — the model chooses which tools to call based on
  the investigation context
- **Termination tool** — `submit_diagnosis` marks the end of the reasoning
  loop; after calling it, the model provides its final summary
- **Repeated-action detection** — calling the same tool with the same arguments
  twice is detected and flagged as a repeated action
- **Budget enforcement** — bounded execution with `max_model_calls=10`,
  `max_tool_calls=8`, and `max_iterations=5`
- **Observable state** — state contains `observations[]`, `actions[]`, and
  `diagnosis` keys; no raw chain-of-thought is exposed
- **Non-convergence handling** — repeated text-only responses without progress
  trigger budget exhaustion
- **Read-only enforcement** — tools don't mutate external state; only
  `submit_diagnosis` records the result

## State contract

```python
class DiagnosisResult(BaseModel):
    category: str       # Incident category (infrastructure, application, network, data)
    root_cause: str     # Identified root cause
    confidence: float   # 0.0–1.0
    evidence: list[str] # Evidence observations
```

## Test scenarios

| Scenario | Description |
|----------|-------------|
| `diagnosis_success` | Happy path: query metrics, logs, deployment history, submit diagnosis |
| `multi_service_diagnosis` | Investigate multiple services before concluding |
| `budget_exhausted` | Model keeps querying metrics without submitting diagnosis |
| `repeated_action` | Model calls same tool with same args twice — flagged as repeated |
| `non_convergence` | Model loops with text-only responses, no progress |
| `read_only_diagnosis` | Diagnosis submitted, verify no external state was mutated |

## Running

```bash
# Run the default scenario (diagnosis_success)
uv run python -m examples.05_react_loop.run

# Run a specific scenario
uv run python -m examples.05_react_loop.run budget_exhausted

# Run all tests
cd /home/rmax-10/src/adk-agentic-patterns && uv run pytest examples/05_react_loop/ -v
```

## Expected output (success)

```json
{
  "status": "succeeded",
  "output": {
    "observations": ["Metric error_rate for api-gateway: 12.3 % (healthy: false)", "..."],
    "actions": [{"tool": "query_metrics", "arguments": {...}, "repeated": false}, "..."],
    "diagnosis": "API Gateway is experiencing elevated error rates due to a recent deployment",
    "termination_reason": "diagnosis_submitted"
  },
  "metrics": {
    "model_calls": 5,
    "tool_calls": 4,
    "iterations": 5
  }
}
```

## Expected output (failure / budget exhausted)

```json
{
  "status": "budget_exhausted",
  "output": {
    "observations": ["Metric cpu_usage for api-gateway: 89.5 % (healthy: false)", "..."],
    "diagnosis": null,
    "termination_reason": "budget_exhausted"
  },
  "metrics": {
    "model_calls": 6,
    "tool_calls": 5,
    "iterations": 6
  }
}
```
