# Pattern 00: Single Structured Model Call

## Problem
Classify a support request into a typed category with one model invocation.

## Pattern
One model call with a Pydantic response schema. No tools, no loops.
This is the simplest possible agentic baseline — it's not even an agent,
just a structured LLM call.

## Why This Pattern Is Justified
- Minimum viable model integration
- Establishes typed contracts as the baseline
- Demonstrates schema enforcement before any orchestration

## Simpler Alternative
Deterministic keyword matching — but the model handles natural language variation.

## ADK Primitives Used
- `LlmAgent` with `output_schema`
- `ScriptedModel` (offline fake model)

## Information Flow
```
User Request → ScriptedModel → ClassificationResult (Pydantic) → Output
```

## Control Flow
```
1. Receive request text
2. One model invocation with output_schema
3. Return typed ClassificationResult
```

## State Model
- No persistent state — stateless single call

## State Ownership Table
| Key | Writer | Readers | Scope |
|-----|--------|---------|-------|
| (none) | — | — | — |

## Tool Permission Table
| Tool | Agent | Permissions |
|------|-------|-------------|
| (none) | — | — |

## Success Termination
Model returns valid `ClassificationResult` with category and confidence.

## Failure Termination
- Missing fixture key
- Malformed model output

## Retry Policy
No retry — single call pattern.

## Execution Budgets
- max_model_calls: 1
- max_tool_calls: 0
- max_iterations: 0

## How to Run Offline
```bash
uv run python -m examples.00_single_model_call.run
uv run python -m examples.00_single_model_call.run billing_issue
uv run pytest examples/00_single_model_call/test_example.py -v
```

## How to Run with Gemini
```bash
PATTERNS_EXECUTION_MODE=live GOOGLE_API_KEY=... uv run python -m examples.00_single_model_call.run
```

## Expected Output
See `expected/success.json` — classification with category, confidence, reasoning.

## Tests Included
- `test_success_billing` — happy path
- `test_success_account` — account classification
- `test_success_technical` — technical classification
- `test_low_confidence_ambiguous` — ambiguous query
- `test_single_model_call_only` — budget enforcement
- `test_audit_events_present` — audit trail

## Common Failure Modes
- Unknown fixture key → `ValueError`
- Missing `output_schema` on agent → unstructured text instead of typed result

## Production-Hardening Requirements
- Replace scripted model with real Gemini/Claude
- Add prompt versioning
- Add model fallback (cheaper model for simple queries)
- Add telemetry export (OpenTelemetry collector)

## Related Patterns
- `prompt-chaining` — when output feeds into another model
- `tool-using-agent` — when the model needs external data

## Anti-Pattern Demonstrated or Avoided
- **Avoided:** Using unstructured text parsing for classification
- **Avoided:** Adding unnecessary tools or loops to a one-shot task
