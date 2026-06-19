# Pattern 22: Observability and Evaluation

## Problem
Instrument a multi-step agent workflow and evaluate recorded traces using deterministic metrics and lightweight OpenTelemetry-like span exports.

## Pattern
A telemetry layer records every step of a 3-stage agent (classify → tool_lookup → answer) as spans in a trace, then evaluates the trace against deterministic policies:

1. **Trace ID & span hierarchy** — root span with child spans (model_call, tool_call, routing, validation, state_transition)
2. **Synthetic token count** — prompt/completion tokens recorded per model_call span
3. **Tool latency** — duration_ms recorded per tool_call span
4. **Task completion result** — evaluator checks root span status
5. **Cost-per-success** — total tokens / 100 (1¢ per 100 tokens) when task completes
6. **Groundedness score** — 1.0 if answer validation passes, else 0.0
7. **Schema-validity rate** — 1.0 if all validation spans pass, else 0.0
8. **Failure category** — 'none' or 'task_failed'
9. **Deterministic evaluators** — task completion, maximum steps, schema validity, forbidden tool usage, state ownership, argument schema alignment, citation correctness

## Why This Pattern Is Justified
- Observability enables debugging, auditing, and cost analysis of agent workflows
- Offline evaluation with deterministic metrics catches regressions before deployment
- Span hierarchies mirror production OpenTelemetry patterns for smooth migration
- Cost-per-success and groundedness scores quantify quality and efficiency

## Simpler Alternative
Print-based logging — less structured, not queryable, no evaluation framework.

## ADK Primitives Used
- `InMemoryExporter` (from `adk_patterns.telemetry`) — lightweight trace collection
- `ScriptedModel` (from `adk_patterns.models`) — deterministic fake model with fixture registry
- `evaluate_task_completion`, `evaluate_maximum_steps`, `evaluate_schema_validity`, `evaluate_forbidden_tool_usage` (from `adk_patterns.telemetry`)

## Information Flow
```
Request Text
       ↓
STEP 1: Model classifies request type (MODEL_CALL span)
       ↓
Validate classification (VALIDATION span)
       ↓
Route decision (ROUTING span)
       ↓
STEP 2: Model calls lookup tool (MODEL_CALL → TOOL_CALL spans)
       ↓
Validate arguments (VALIDATION span)
       ↓
STEP 3: Model synthesizes answer (MODEL_CALL span)
       ↓
Validate answer (VALIDATION span)
       ↓
Evaluators run against collected trace
```

## Control Flow
```
1. Create trace + root span
2. Classify request (step 1, MODEL_CALL)
3. Validate classification
4. Route decision (ROUTING)
5. Tool lookup (step 2, MODEL_CALL → TOOL_CALL)
6. Validate arguments
7. Synthesize answer (step 3, MODEL_CALL)
8. Validate answer
9. Run 7 deterministic evaluators on trace
10. Compute synthetic metrics (cost, groundedness, schema rate)
11. Return trace, evaluations, and metrics
```

## State Model
Each workflow step writes to isolated state keys via span `state_transition` events.

## State Ownership Table
| State key | Writer span kind | Readers | Scope |
|-----------|-----------------|---------|-------|
| classification | MODEL_CALL | ROUTING, TOOL_CALL | Run |
| selected_tool | ROUTING | TOOL_CALL | Run |
| tool_request | MODEL_CALL | TOOL_CALL | Run |
| tool_result | TOOL_CALL | MODEL_CALL (answer) | Run |
| final_answer | MODEL_CALL | Output | Run |
| tool_latency | STATE_TRANSITION | Metrics | Run |
| workflow_status | INTERNAL | Output | Run |

## Tool Permission Table
| Tool | Agent | Permissions |
|------|-------|-------------|
| lookup_tool | Main | query, type arguments |
| exec_shell | (forbidden) | blocked |

## Success Termination
All steps complete, all validation spans pass, and no forbidden tools are used.

## Failure Termination
- Empty or invalid classification → FAILED
- Schema validation failure → FAILED
- Forbidden tool used → flagged by evaluator
- State key violation → flagged by evaluator

## Retry Policy
No retry — this pattern focuses on observability, not recovery. Retry policies are demonstrated in Pattern 18.

## Execution Budgets
- max_model_calls: 3
- max_tool_calls: 2

## How to Run Offline
```bash
uv run python -m examples.22_observability_and_evaluation.run
uv run python -m examples.22_observability_and_evaluation.run success
uv run python -m examples.22_observability_and_evaluation.run failure
uv run pytest examples/22_observability_and_evaluation/test_example.py -v
```

## How to Run with Gemini
```bash
PATTERNS_EXECUTION_MODE=live GOOGLE_API_KEY=... uv run python -m examples.22_observability_and_evaluation.run
```

## Expected Output
See `expected/success.json` — successful trace with completion=True and all evaluation results.
See `expected/failure.json` — failed trace (empty request) with failure category.

## Tests Included
- `test_trace_structure` — trace has root span with child spans
- `test_model_call_spans` — model_call spans recorded with durations
- `test_tool_call_spans` — tool_call spans with tool_name attribute
- `test_evaluator_task_completion` — traces evaluated, completion=True
- `test_evaluator_maximum_steps` — step budget compliance check
- `test_evaluator_maximum_steps_exceeded` — exceeding budget detected
- `test_evaluator_schema_validity` — validation spans OK
- `test_evaluator_forbidden_tool_usage_passes` — no forbidden tools
- `test_evaluator_forbidden_tool_usage_detected` — forbidden tools detected
- `test_evaluator_state_ownership_passes` — no state violations
- `test_evaluator_state_ownership_violation` — state key violations detected
- `test_state_ownership_in_agent_run_success` — workflow produces clean state
- `test_state_ownership_in_agent_run_violation` — violation scenario detected
- `test_synthetic_token_tracking` — token counts in span attributes
- `test_synthetic_tokens_in_metrics` — metrics include token counts
- `test_success_scenario` — full pipeline end-to-end
- `test_failure_scenario` — failure scenario output structure
- `test_forbidden_tool_scenario` — forbidden tool evaluation

## Common Failure Modes
- Missing fixture key → ScriptedModel returns default empty response
- Empty request → classification may be empty
- Forbidden tool call → evaluator flags violation
- State key writes to disallowed keys → evaluator flags violation

## Production-Hardening Requirements
- Replace InMemoryExporter with real OpenTelemetry SDK exporter (e.g., OTLP)
- Add distributed trace context propagation across service boundaries
- Export traces to Jaeger, Zipkin, or cloud trace stores
- Add real token tracking from model API responses
- Add real latency instrumentation (not synthetic sleep)
- Add alerting rules for evaluator failures
- Add retention policies for trace storage
- Integrate with Prometheus/Loki for metric aggregation

## Related Patterns
- `single-model-call` — baseline single-call structure
- `budget-aware-model-routing` — token budget tracking and cost-per-success
- `retry-fallback-recovery` — retry logic for failure recovery

## Anti-Pattern Demonstrated or Avoided
- **Demonstrated:** Lightweight in-memory trace collection for offline testing
- **Avoided:** Missing observability — every step is recorded as a typed span
- **Avoided:** Untested evaluation logic — all evaluators have explicit tests
- **Avoided:** Ignoring state ownership — checked by deterministic evaluator
