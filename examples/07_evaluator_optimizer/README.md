# Pattern 07: Evaluator-Optimizer

## Problem
Generate a technical change proposal and iteratively improve it against a rubric. A single model call often produces a first draft that lacks depth, misses sections, or scores poorly on specific criteria. Manual iterative refinement is time-consuming and inconsistent.

## Pattern
Two logically separate roles — a **Maker** (proposal generator) and a **Checker** (rubric evaluator) — run in a tight feedback loop. The Maker produces or improves a proposal; the Checker scores it on four rubric dimensions (clarity, completeness, feasibility, risk assessment) and returns per-section feedback. The loop terminates when:

1. **Convergence** — overall score >= 0.8 → `SUCCEEDED`
2. **No progress** — score flat for 2 consecutive iterations → `PARTIAL`
3. **Max iterations** — 4 iterations exhausted → `PARTIAL` with best draft
4. **Evaluator failure** — checker raises an error → `PARTIAL` with last good draft

## Why This Pattern Is Justified
- Single-shot LLM proposals are often mediocre
- Iterative refinement with structured feedback mimics human peer review
- The pattern is bounded (max 4 iterations, 8 model calls) so it won't run forever
- No-progress detection prevents wasting budget on flat scores

## Simpler Alternative
Ask the model to self-critique (same-model evaluator). But an independent evaluator catches different issues — this pattern supports both approaches and lets you compare them.

## ADK Primitives Used
- `ScriptedModel` with `set_response_sequence()` for deterministic iteration testing
- `RunContext` for budget tracking, audit events, and state snapshots
- Pydantic contracts (`Proposal`, `RubricScores`) for typed inter-component communication

## Information Flow
```
User Request → Maker → Proposal (typed)
                  ↓
            Checker → RubricScores (typed w/ per-section feedback)
                  ↓
            Score >= 0.8? ──yes──→ SUCCEEDED
                  ↓ no
            No progress? ──yes──→ PARTIAL (no_progress)
                  ↓ no
            Max iterations? ──yes──→ PARTIAL (max_iterations)
                  ↓ no
            Checker error? ──yes──→ PARTIAL (fallback to best draft)
                  ↓ no
            → Maker (improve with feedback) → loop
```

## Control Flow
```
1. Maker generates initial proposal
2. Checker evaluates proposal against rubric
3. If score >= 0.8 → return SUCCEEDED with final proposal
4. If score hasn't improved for 2 iterations → return PARTIAL (no_progress)
5. If checker raises error → return PARTIAL with best previous draft
6. If iteration < 4 → Maker improves proposal using feedback → goto 2
7. Return PARTIAL with best draft (max_iterations)
```

## State Model
| Key | Writer | Readers | Scope |
|-----|--------|---------|-------|
| `draft` | Maker | Checker, Output | Current iteration |
| `scores{}` | Checker | Loop decision, Output | Per-iteration history |
| `iteration` | Loop | Budget check, Maker | Current iteration number |
| `best_draft` | Loop | Output (fallback) | Best across iterations |
| `best_score` | Loop | No-progress detection | Highest score seen |

## State Ownership Table
| Key | Writer | Readers | Scope |
|-----|--------|---------|-------|
| `draft` | Maker | Checker, Output | Per iteration |
| `scores{}` | Checker | Loop, Output | Per iteration |
| `iteration` | Loop | All | Monotonic counter |
| `best_draft` | Loop | Output | Cross-iteration |
| `best_score` | Loop | No-progress check | Cross-iteration |

## Tool Permission Table
No external tools — the pattern uses only model calls.

## Success Termination
- `SUCCEEDED` — overall score >= 0.8 within 4 iterations
- Output contains final `draft`, `scores`, `iterations`, and `status: "converged"`

## Failure Termination
- `PARTIAL` — max iterations (4) reached without convergence
- `PARTIAL` — no score improvement for 2 consecutive iterations
- `PARTIAL` — evaluator error, using best previous draft as fallback

## Retry Policy
No retry — the pattern itself is the refinement mechanism.

## Execution Budgets
- `max_model_calls`: 8 (2 per iteration × 4 iterations)
- `max_tool_calls`: 0
- `max_iterations`: 4

## How to Run Offline
```bash
uv run python -m examples.07_evaluator_optimizer.run
uv run python -m examples.07_evaluator_optimizer.run converge
uv run pytest examples/07_evaluator_optimizer/test_example.py -v
```

## How to Run with Gemini
```bash
PATTERNS_EXECUTION_MODE=live GOOGLE_API_KEY=... uv run python -m examples.07_evaluator_optimizer.run
```

## Expected Output
See `expected/success.json` — converged proposal with score >= 0.8.
See `expected/failure.json` — max iterations with best draft and PARTIAL status.

## Tests Included
- `test_converges` — 3 iterations, score improves to 0.82 → `SUCCEEDED`
- `test_converges_with_threshold_met` — final score >= 0.8, draft present
- `test_max_iterations_reached` — 4 iterations, all < 0.8 → `PARTIAL`
- `test_max_iterations_all_scores_below_threshold` — scores all < 0.8
- `test_no_progress_detection` — flat score for 2 iterations → stops early
- `test_evaluator_failure_fallback` — checker error on 2nd eval → uses best draft
- `test_independent_vs_same_evaluator` — different checker fixtures give different scores
- `test_rubric_localized_feedback` — each section gets specific feedback
- `test_state_keys_present` — state has draft, scores{}, iteration, best_draft, best_score
- `test_budget_max_model_calls` — exactly 8 model calls for 4 iterations
- `test_audit_events_present` — audit trail recorded

## Common Failure Modes
- Missing fixture key → returns `PARTIAL` with evaluator_failure_fallback
- Maker fixture not found → `FAILED`
- All checker fixture keys exhausted → loops use last registered key

## Production-Hardening Requirements
- Replace scripted model with real Gemini/Claude
- Add model-specific rubric adaptation (different models weight criteria differently)
- Add human-in-the-loop for threshold override
- Add telemetry export (OpenTelemetry collector)
- Track per-iteration latency and cost

## Related Patterns
- `prompt-chaining` — when each step is a one-shot improvement (no loop)
- `parallel-fanout-gather` — when multiple independent evaluators run concurrently
- `bounded-loop-agent` — general iteration pattern with budget enforcement

## Anti-Pattern Demonstrated or Avoided
- **Avoided:** Unbounded iteration without progress check
- **Avoided:** Self-evaluation without independent checker
- **Demonstrated:** Separating maker and checker fixture sets for testability
- **Demonstrated:** Typed feedback contracts that the maker can consume programmatically
