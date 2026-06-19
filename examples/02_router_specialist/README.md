# Pattern 02: Router-Specialist

## Problem
Route customer support requests to the appropriate specialist (billing, account, or technical) with isolated tool sets and confidence-based fallback.

## Pattern
A two-phase pattern:
1. **Router** — Classifies the request into a specialist route with a confidence score
2. **Specialist** — Handles the request using its own isolated tool set

Two router variants are provided:
- **Model-driven router** — Uses an LLM to classify the request
- **Rule-driven router** — Uses deterministic keyword matching (no model call)

## Why This Pattern Is Justified
- Separates routing logic from domain-specific handling
- Isolated tool sets prevent cross-domain access
- Confidence threshold prevents low-quality routing
- Deterministic fallback for unknown or ambiguous queries

## Simpler Alternative
Single agent with all tools — but routing enables specialized handling and security isolation.

## ADK Primitives Used
- `ScriptedModel` (offline fake model for deterministic testing)
- `structured_response` (fixture-based model responses)
- `RunContext` (budget tracking, audit events, state snapshots)

## Information Flow
```
User Request → Router (model or rule) → RouterVerdict (Pydantic) → Specialist → SpecialistOutput
                                  ↓
                    Confidence < 0.6 → General Specialist
```

## Control Flow
```
1. Receive customer request text
2. Route request (model-driven or rule-driven)
3. If confidence < 0.6, override route to 'general'
4. Dispatch to appropriate specialist with isolated tool set
5. Specialist executes tools and produces response
6. Return route_verdict + specialist_output
```

## State Model
- Transient state per request — no persistent storage
- State keys: `route_verdict`, `specialist_output`

## State Ownership Table
| Key | Writer | Readers | Scope |
|-----|--------|---------|-------|
| route_verdict | Router | Specialist dispatch | Per-request |
| specialist_output | Specialist | Output | Per-request |

## Tool Permission Table
| Tool Set | Owner Specialist | Permissions |
|----------|-----------------|-------------|
| lookup_invoice, process_refund | billing | billing only |
| reset_password, send_verification_email | account | account only |
| check_api_status, query_logs | technical | technical only |
| (none) | general | — |

## Success Termination
Valid routing verdict → specialist handles request → typed SpecialistOutput returned.

## Failure Termination
- Unknown fixture key
- Permission violation (specialist using wrong tool set)
- Budget exhausted

## Retry Policy
No retry — single-pass routing and handling.

## Execution Budgets
- max_model_calls: 2
- max_tool_calls: 5
- max_iterations: 0

## How to Run Offline
```bash
uv run python -m examples.02_router_specialist.run
uv run python -m examples.02_router_specialist.run billing_route
uv run python -m examples.02_router_specialist.run --rule      # rule-driven variant
uv run pytest examples/02_router_specialist/test_example.py -v
```

## How to Run with Gemini
```bash
PATTERNS_EXECUTION_MODE=live GOOGLE_API_KEY=... uv run python -m examples.02_router_specialist.run
```

## Expected Output
See `expected/success.json` — billing route with verdict and specialist response.
See `expected/failure.json` — unknown route falling back to general.

## Tests Included
- `test_billing_route` — routes correctly to billing specialist
- `test_account_route` — routes to account specialist
- `test_low_confidence_fallback` — confidence < 0.6 routes to general
- `test_unknown_route` — unknown route goes to fallback
- `test_ambiguous_route` — ambiguous query goes to general
- `test_rule_driven_variant` — deterministic router without model
- `test_isolated_tools` — billing specialist cannot access technical tools
- `test_router_confusion_matrix` — confusion-matrix scenarios
- `test_state_keys` — route_verdict and specialist_output present
- `test_budget_enforcement` — budget limits respected

## Common Failure Modes
- Low-confidence routing → falls back to general (handled)
- Unknown route → falls back to general (handled)
- Specialist tries to use wrong tool → PermissionError (handled)
- Missing fixture key → ValueError

## Production-Hardening Requirements
- Replace scripted model with real Gemini/Claude
- Add prompt versioning
- Add model fallback (cheaper model for simple queries)
- Add telemetry export (OpenTelemetry collector)
- Add A/B testing between model-driven and rule-driven router

## Related Patterns
- `single-model-call` — simpler classification without routing
- `tool-using-agent` — when the specialist needs external data
- `guardrails-policy-gate` — for pre-routing policy checks

## Anti-Pattern Demonstrated or Avoided
- **Avoided:** Passing all tools to a single agent (security risk)
- **Avoided:** Hard-coding routing without confidence threshold
- **Avoided:** Using unstructured text for routing decisions
- **Demonstrated:** Both model-driven and rule-driven routing variants
