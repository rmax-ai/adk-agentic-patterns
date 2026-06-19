# Pattern 09: Sequential Specialists

## Problem
Process an insurance claim through four sequential specialist stages:
1. **Extraction** — Parse raw submission text into structured claim data
2. **Eligibility** — Determine if the claim is covered by the policy
3. **Fraud Screening** — Detect potential fraud indicators
4. **Explanation** — Generate a human-readable claim decision

Each specialist has **one typed responsibility**. Output from stage N is the **only input** to stage N+1 — no shared memory, no message passing, no "personalities."

## Pattern
A deterministic pipeline of four typed model calls. Each stage produces a Pydantic-validated output contract that feeds the next stage. The pipeline can terminate early at the eligibility or fraud stage if the claim is ineligible or suspicious.

## Why This Pattern Is Justified
- **Typed contracts between stages** — no ad-hoc dict passing, no schema drift
- **Early termination** — ineligible claims don't waste fraud screening budget
- **Deterministic handoff** — each specialist works from validated inputs only
- **Isolation** — a bug in one stage's output schema can't corrupt another stage

## How This Differs from Arbitrary Multi-Agent Role Play
| Aspect | Sequential Specialists | Arbitrary Multi-Agent Role Play |
|--------|----------------------|--------------------------------|
| Communication | Typed Pydantic contracts | Chat history / open messages |
| Scope | One responsibility per specialist | Vague "personas" with overlapping scope |
| Termination | Deterministic pipeline, early exit | Conversational, no defined endpoints |
| State isolation | Each stage writes its own keys | Shared memory, cross-contamination risk |
| Testability | Each stage testable in isolation | Requires full conversation simulation |

## ADK Primitives Used
- `ScriptedModel` (offline fake model)
- `RunContext` / `run_scope` with budget tracking
- `structured_response` for typed model output simulation

## Information Flow
```
Raw Claim Text
      ↓
┌─ Stage 1: Extraction ──────────┐
│  ExtractedClaim (Pydantic)     │
└────────────────────────────────┘
      ↓
┌─ Stage 2: Eligibility ──────────┐
│  EligibilityVerdict (Pydantic)  │
│  └→ is_eligible=False → STOP   │
└────────────────────────────────┘
      ↓
┌─ Stage 3: Fraud Screening ─────┐
│  FraudScreeningResult (Pydantic)│
│  └→ is_suspicious=True → STOP  │
└────────────────────────────────┘
      ↓
┌─ Stage 4: Explanation ─────────┐
│  ClaimExplanation (Pydantic)    │
└────────────────────────────────┘
      ↓
Final Output (all 4 state keys)
```

## Control Flow
1. Receive raw claim submission text
2. Stage 1: Extract → `ExtractedClaim`
3. Stage 2: Check eligibility → `EligibilityVerdict` (stop if ineligible)
4. Stage 3: Screen fraud → `FraudScreeningResult` (stop if suspicious)
5. Stage 4: Explain → `ClaimExplanation`
6. Return aggregated output with all state keys

## State Model
- State is accumulated per stage — each stage writes exactly one key
- No shared mutable state between stages
- Early termination preserves all state written so far

## State Ownership Table

| Key | Writer | Readers | Scope |
|-----|--------|---------|-------|
| `extracted_claim` | Stage 1 (Extraction) | Stage 2 | Snapshot |
| `eligibility_result` | Stage 2 (Eligibility) | Stage 3 | Snapshot |
| `fraud_result` | Stage 3 (Fraud Screening) | Stage 4 | Snapshot |
| `explanation` | Stage 4 (Explanation) | Output | Snapshot |

## Tool Permission Table
| Tool | Agent | Permissions |
|------|-------|-------------|
| (none) | — | — |

No tools — pure model invocations with structured output schemas.

## Success Termination
All four stages complete successfully. Final output contains all four state keys with validated Pydantic models.

## Failure Termination
- Stage N returns no structured output (model failure)
- Stage N output fails Pydantic schema validation
- Early termination is NOT a failure — ineligible and fraud-detected claims produce valid partial outputs

## Retry Policy
No retry — deterministic pipeline with schema validation guards.

## Execution Budgets
- max_model_calls: 4
- max_tool_calls: 0
- max_iterations: 0

## How to Run Offline
```bash
uv run python -m examples.09_sequential_specialists.run
uv run python -m examples.09_sequential_specialists.run valid_auto
uv run python -m examples.09_sequential_specialists.run ineligible
uv run python -m examples.09_sequential_specialists.run fraud_suspicious
uv run pytest examples/09_sequential_specialists/test_example.py -v
```

## How to Run with Gemini
```bash
PATTERNS_EXECUTION_MODE=live GOOGLE_API_KEY=... uv run python -m examples.09_sequential_specialists.run
```

## Expected Output
See `expected/success.json` — all 4 state keys with validated claim, eligibility, fraud screening, and explanation data.
See `expected/failure.json` — stops at eligibility with ineligible verdict.

## Tests Included
- `test_valid_claim_auto` — happy path (all 4 stages)
- `test_valid_claim_property` — property damage claim
- `test_ineligible_claim_stops_at_eligibility` — stops at stage 2
- `test_fraud_detected_stops_at_fraud` — stops at stage 3
- `test_all_four_stages_populated` — all state keys present
- `test_stage_isolation` — no key cross-contamination
- `test_audit_events_present` — audit trail from all stages
- `test_budget_enforcement` — budget limits respected

## Common Failure Modes
- Missing fixture key → falls back to default fixture
- No structured output from model → marks stage failed
- Schema validation failure → marks stage failed, pipeline stops
- Stage 2 ineligible → pipeline terminates with 2 model calls
- Stage 3 suspicious → pipeline terminates with 3 model calls

## Production-Hardening Requirements
- Replace scripted model with real Gemini/Claude
- Add per-stage retry with circuit breaker
- Add telemetry export per specialist
- Add human-in-the-loop for fraud-escalated claims
- Store intermediate state snapshots in durable storage

## Related Patterns
- `prompt-chaining` — general sequential pipeline without domain-specific contracts
- `router-specialist` — when you need to dynamically route to the right specialist
- `parallel-fanout-gather` — when specialists can run concurrently

## Anti-Pattern Demonstrated or Avoided
- **Avoided:** Allowing specialists to "chat" with each other via shared history
- **Avoided:** Passing raw dicts between stages without schema validation
- **Avoided:** One monolithic agent doing extraction, eligibility, fraud, and explanation
- **Avoided:** Making stage 4 (or any downstream stage) depend on raw text that stage 1 already parsed
