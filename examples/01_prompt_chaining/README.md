# Pattern 01: Prompt Chaining

## Problem
Transform a raw product incident report through three sequential stages:
1. **Normalized facts extraction** — parse unstructured text into structured `IncidentFacts`
2. **Severity assessment** — evaluate severity from normalized facts
3. **Stakeholder summary** — generate an executive summary for stakeholders

## Pattern
Three model calls in strict sequence, each with its own Pydantic response schema.
The output of each stage feeds the next. If any stage fails schema validation,
the chain stops immediately — no downstream stage executes.

## Why This Pattern Is Justified
- Each stage has a distinct responsibility and schema
- Intermediate validation catches errors early
- Clear separation of concerns between extraction, analysis, and communication
- Downstream stages never see raw/malformed data

## Simpler Alternative
A single monolithic model call with all three outputs — but validation granularity
and failure isolation are lost.

## ADK Primitives Used
- `ScriptedModel` (offline fake model with fixture registry)
- Manual sequential chaining via Python control flow

## Information Flow
```
Raw Incident Report
       ↓
Stage 1: IncidentFacts (Pydantic)
       ↓
Stage 2: SeverityAssessment (Pydantic)
       ↓
Stage 3: StakeholderSummary (Pydantic)
       ↓
Aggregated Output
```

## Control Flow
```
1. Receive raw incident report text
2. Stage 1: model call → validate IncidentFacts → fail fast if invalid
3. Stage 2: model call → validate SeverityAssessment → fail fast if invalid
4. Stage 3: model call → validate StakeholderSummary → fail fast if invalid
5. Return aggregated output with all three state keys
```

## State Model
Each stage writes to its own isolated state key. No cross-contamination.

## State Ownership Table

| Key | Writer | Readers | Scope |
|-----|--------|---------|-------|
| stage1_facts | Stage 1 | Stage 2, Stage 3, Output | Pipeline |
| stage2_severity | Stage 2 | Stage 3, Output | Pipeline |
| stage3_summary | Stage 3 | Output | Pipeline |

## Tool Permission Table

| Tool | Agent | Permissions |
|------|-------|-------------|
| (none) | — | — |

## Success Termination
All three stages return valid Pydantic models. Output contains all three state keys.

## Failure Termination
- Stage 1 schema validation fails → chain stops, status FAILED, only 1 model call consumed
- Stage 2 schema validation fails → chain stops after 2 calls
- Stage 3 schema validation fails → chain stops after 3 calls

## Retry Policy
No retry — strict sequential chain with upstream validation gates.

## Execution Budgets
- max_model_calls: 3
- max_tool_calls: 0
- max_iterations: 0

## How to Run Offline
```bash
uv run python -m examples.01_prompt_chaining.run
uv run python -m examples.01_prompt_chaining.run security_breach
uv run python -m examples.01_prompt_chaining.run malformed_facts
uv run pytest examples/01_prompt_chaining/test_example.py -v
```

## How to Run with Gemini
```bash
PATTERNS_EXECUTION_MODE=live GOOGLE_API_KEY=... uv run python -m examples.01_prompt_chaining.run
```

## Expected Output
See `expected/success.json` — aggregated output with all three state keys.
See `expected/failure.json` — failure output when upstream validation fails.

## Tests Included
- `test_success_security_breach` — happy path, 3 stages, 3 model calls
- `test_success_latency_outage` — latency outage scenario
- `test_success_degraded_performance` — CDN degradation scenario
- `test_malformed_upstream_stops_downstream` — malformed facts → chain stops at stage 1
- `test_all_three_stages_populated` — all 3 state keys present in output
- `test_state_key_isolation` — no cross-contamination between stage keys
- `test_audit_events_present` — audit events from all 3 stages
- `test_budget_enforcement` — max_model_calls=3, max_iterations=0

## Common Failure Modes
- Missing fixture key → `ScriptedModel` returns default empty response
- Missing required field in fixture → Pydantic `ValidationError` → chain stops
- Stage 1 fails → stages 2 and 3 never run → only 1 model call consumed

## Production-Hardening Requirements
- Replace scripted model with real Gemini/Claude
- Add structured output schema enforcement via model API
- Add intermediate output persistence for resumability
- Add circuit breaker per stage (retry with backoff for transient failures)
- Add telemetry export per stage (OpenTelemetry)
- Add approval gate between stage 2 and stage 3 (human-in-the-loop)

## Related Patterns
- `single-model-call` — baseline single-call structure
- `routing` — when the path through stages is conditional
- `evaluator-optimizer` — when stages iterate via feedback

## Anti-Pattern Demonstrated or Avoided
- **Avoided:** Passing unstructured text between stages
- **Avoided:** Continuing the chain after a stage failure
- **Avoided:** Shared mutable state between stages (each stage owns its key)
