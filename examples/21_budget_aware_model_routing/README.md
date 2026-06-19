# Pattern 21: Budget-Aware Model Routing

## Problem
Route requests of varying complexity (simple, medium, complex) to appropriate fake model tiers while respecting token budgets and handling validation failures through escalation.

## Pattern
A routing layer classifies each request by complexity, routes it to the cheapest adequate model tier, tracks token budgets, and provides fallback/escalation mechanisms:
1. **Deterministic classifier** — request length determines complexity
2. **Model-based fallback** — complexity class→model tier mapping
3. **Per-tier metadata** — cost and latency per tier (cheap/medium/expensive)
4. **Token budget tracking** — synthetic token consumption monitoring
5. **Budget exhaustion fallback** — expensive → cheaper tier when budget low
6. **Validation failure escalation** — cheap → expensive when validation fails
7. **Escalation cap** — max 2 escalations, then FAILED status
8. **Cost-per-success** — total cost divided by successful results

## Why This Pattern Is Justified
- Different request complexities have different cost/quality tradeoffs
- Budget enforcement prevents runaway costs
- Escalation provides graceful degradation on validation failure
- Cost-per-success metric enables cost optimization analysis

## Simpler Alternative
A single model tier for all requests — simpler but wasteful for simple tasks and potentially insufficient for complex ones.

## ADK Primitives Used
- `ScriptedModel` (offline fake model with fixture registry)
- `RunContext` (budget tracking, audit events, state snapshots)
- `RunBudget` (budget constraints)

## Information Flow
```
Request Text
       ↓
Complexity Classifier (deterministic: length-based)
       ↓
Model Tier Router (simple→cheap, medium→medium, complex→expensive)
       ↓
Model Invocation (with fixture key)
       ↓
Validation (response text check)
       ↓
Success ← OR → Escalation (if validation fails, max 2)
                 ↓
               Fallback (if budget exhausted, to cheaper tier)
```

## Control Flow
```
1. Classify request complexity (deterministic: <80=simple, <200=medium, else=complex)
2. Route to initial tier based on complexity
3. Loop (max 3 attempts = initial + 2 escalations):
   a. Check budget → fallback to cheaper tier if exhausted
   b. Invoke model with appropriate fixture
   c. Validate response → break on success
   d. Escalate to next tier on failure (max 2 escalations)
4. Return routing decision, model tier, cost, and result
```

## State Model
Each routing step writes to isolated state keys.

## State Ownership Table

| Key | Writer | Readers | Scope |
|-----|--------|---------|-------|
| routing_decision | Router | Output | Run |
| model_tier | Router | Output | Run |
| cost | Router | Output | Run |
| result | Router | Output | Run |

## Tool Permission Table

| Tool | Agent | Permissions |
|------|-------|-------------|
| (none) | — | — |

## Success Termination
Valid response received from a model tier within budget and escalation limits.

## Failure Termination
- Max escalations (2) reached without valid response → status FAILED
- Budget exhausted with no cheaper fallback → status BUDGET_EXHAUSTED

## Retry Policy
No retry — escalation handles validation failures. Budget fallback handles budget exhaustion.

## Execution Budgets
- max_model_calls: 4
- max_tool_calls: 0
- max_iterations: 0
- max_synthetic_tokens: 5000

## How to Run Offline
```bash
uv run python -m examples.21_budget_aware_model_routing.run
uv run python -m examples.21_budget_aware_model_routing.run simple
uv run python -m examples.21_budget_aware_model_routing.run complex
uv run pytest examples/21_budget_aware_model_routing/test_example.py -v
```

## How to Run with Gemini
```bash
PATTERNS_EXECUTION_MODE=live GOOGLE_API_KEY=... uv run python -m examples.21_budget_aware_model_routing.run
```

## Expected Output
See `expected/success.json` — successful routing output with all four state keys.
See `expected/failure.json` — failure output when max escalations are reached.

## Tests Included
- `test_simple_routed_to_cheap` — simple request uses cheap model
- `test_medium_routed_to_medium` — medium request uses medium model
- `test_complex_routed_to_expensive` — complex request uses expensive model
- `test_budget_exhausted_fallback` — token budget exceeded, fallback to cheap
- `test_validation_failure_escalation` — cheap model fails validation, escalate
- `test_no_infinite_escalation` — 2 escalations max, then FAILED
- `test_cost_per_success` — cost-per-success in metrics
- `test_state_keys_present` — all 4 state keys present in output

## Common Failure Modes
- Missing fixture key → ScriptedModel returns default empty response
- All tiers fail validation → max escalations reached, FAILED
- Budget exhausted → BUDGET_EXHAUSTED status

## Production-Hardening Requirements
- Replace deterministic classifier with ML-based complexity estimation
- Add real cost tracking (API billing data)
- Add dynamic budget tuning based on historical usage
- Add circuit breaker per tier (rate limiting, quota management)
- Add telemetry export per routing decision (OpenTelemetry)
- Add A/B testing for tier selection policy

## Related Patterns
- `single-model-call` — baseline single-call structure
- `evaluator-optimizer` — loop with feedback for quality improvement
- `prompt-chaining` — sequential stages with different model tiers

## Anti-Pattern Demonstrated or Avoided
- **Avoided:** Using expensive model for simple requests
- **Avoided:** Infinite escalation loops (cap at 2)
- **Avoided:** Ignoring budget constraints
- **Avoided:** Silent validation failures (escalation provides traceability)
