# Pattern 08: Bounded Loop Agent

**Phase:** 1 · **Autonomy:** Low (3/10) · **Determinism:** High (8/10)

## Scenario

Draft and validate a compliance report until all required sections are present.
The agent iteratively drafts a compliance report, validates it against a fixed checklist,
and refines it based on feedback. Execution is bounded by explicit budgets.

## Required sections

- `executive_summary`
- `methodology`
- `findings`
- `recommendations`
- `signatures`

## Contracts

| Contract | Fields | Description |
|----------|--------|-------------|
| `ComplianceReport` | `sections{}`, `complete: bool`, `issues[]` | A compliance report with named sections |
| `SectionValidation` | `missing[]`, `suggestions[]` | Validation result against the checklist |

## What it demonstrates

- **Bounded loop** — a `while` loop with explicit `RunBudget` checks at each
  iteration
- **Iterative refinement** — each iteration uses validation feedback to improve
  the draft
- **Budget enforcement** — `max_model_calls=6`, `max_iterations=5` terminate
  non-converging runs
- **Partial results** — when budget is exhausted, the best draft so far is
  returned with `BUDGET_EXHAUSTED` status
- **Early stopping** — if all sections pass validation, the loop stops
  immediately
- **State tracking** — `draft`, `missing_sections[]`, `iteration`, and `status`
  are persisted in state snapshots
- **Section validation** — each iteration validates the draft against the
  required 5-section checklist

## Test scenarios

| Scenario | Description |
|----------|-------------|
| `converges` | Loop runs 2-3 iterations, all sections present, passes |
| `budget_exhausted` | Loop hits budget, returns partial result with `BUDGET_EXHAUSTED` |
| `stop_on_pass` | First draft is already complete, loop stops immediately |

## Running

```bash
# Run the default scenario (converges)
uv run python -m examples.08_bounded_loop_agent.run

# Run a specific scenario
uv run python -m examples.08_bounded_loop_agent.run budget_exhausted

# Run all tests
cd /home/rmax-10/src/adk-agentic-patterns && uv run pytest examples/08_bounded_loop_agent/ -v
```

## Expected output

```json
{
  "status": "succeeded",
  "output": {
    "draft": {
      "sections": {
        "executive_summary": "...",
        "methodology": "...",
        "findings": "...",
        "recommendations": "...",
        "signatures": "..."
      },
      "complete": true,
      "issues": []
    },
    "missing_sections": [],
    "iteration": 2,
    "status": "PASSED"
  },
  "metrics": {
    "model_calls": 6,
    "tool_calls": 0,
    "iterations": 3
  }
}
```
