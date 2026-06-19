# Pattern 20: Dynamic Workflow

## Problem
Process a data-quality incident where execution branches depend on discovered
conditions. The system must classify the incident type, then route to the
appropriate handler without further model involvement.

## Pattern
One model call to **classify** the incident type, followed by pure Python
control flow (dict dispatch — equivalent to if/elif/else) to route execution
to the correct branch function. Each branch is a nested deterministic function
with bounded iteration (no recursion). State transitions are explicitly
recorded in `state_snapshot`.

## Why This Pattern Is Justified
- Classification is the only step that benefits from an LLM (understanding
  natural-language descriptions).
- Routing and branch logic are pure data manipulation — ordinary code is
  cheaper, faster, and more deterministic than a model call.
- Explicit state transitions make the execution path auditable.
- Each branch can be unit-tested independently.

## Simpler Alternative
A single model call that both classifies and resolves — but then you lose
deterministic branch guarantees and auditability of the routing decision.

## ADK Primitives Used
- `ScriptedModel` (offline fake model) — used only for the initial
  classification
- Pure Python branch functions (no model calls in branches)
- `RunContext` for audit, budget, and state snapshot tracking

## Information Flow
```
Incident Report (raw text)
       ↓
Classification (1 model call)
       ↓
   [if/elif dispatch]
       ↓
  ┌─────┬─────┬─────┬─────────┐
  │     │     │     │         │
  ↓     ↓     ↓     ↓         ↓
schema missing stale unknown
violation data  data  → escalate
   ↓      ↓      ↓
resolution resolution resolution
```

## Control Flow
1. Receive raw incident report text
2. **Classify** incident type via single model call
3. **Route** via pure Python dispatch based on `incident_type`
4. Branch executes deterministic sub-check:
   - `schema_violation` → `validate_schema` (constraint checks)
   - `missing_data` → `assess_completeness` (gap analysis)
   - `stale_data` → `check_freshness` (timestamp validation)
   - `unknown` → `escalate_to_analyst` (human escalation)
5. Each branch records state transitions and resolution

## State Model
Explicit state transitions recorded in `state_snapshot`. Every transition has
a `from`, `to`, and `reason`.

### State Ownership Table
| Key | Writer | Readers | Scope |
|-----|--------|---------|-------|
| `incident_type` | Classification | Router, Output | Pipeline |
| `classification` | Classification | Output | Pipeline |
| `branch_path` | Router + Branch | Output | Pipeline |
| `transitions` | Branch | Output | Pipeline |
| `resolution` | Branch | Output | Pipeline |

### Tool Permission Table
No tools — all branch logic is pure Python.

### Success Termination
Incident is classified and resolved through one of the four branches.
Output contains `incident_type`, `classification`, and `resolution`.

### Failure Termination
If classification returns no `incident_type`, it defaults to `unknown` and
triggers human escalation. No hard failure — the system always produces a
resolution.

### Retry Policy
No retry needed. Only 1 model call per run; routing and branch logic are
deterministic and stateless.

### Execution Budgets
- max_model_calls: 3
- max_tool_calls: 0
- max_iterations: 3

## How to Run Offline
```bash
uv run python -m examples.20_dynamic_workflow.run
uv run python -m examples.20_dynamic_workflow.run schema_violation
uv run python -m examples.20_dynamic_workflow.run missing_data
uv run python -m examples.20_dynamic_workflow.run stale_data
uv run python -m examples.20_dynamic_workflow.run unknown
uv run pytest examples/20_dynamic_workflow/test_example.py -v
```

## How to Run with Gemini
```bash
PATTERNS_EXECUTION_MODE=live GOOGLE_API_KEY=... \
  uv run python -m examples.20_dynamic_workflow.run
```

## Expected Output
See `expected/success.json` — schema violation branch output.
See `expected/failure.json` — unknown branch output (human escalation).

## Tests Included
- `test_schema_violation_branch` — schema violation → validate_schema
- `test_missing_data_branch` — missing data → assess_completeness
- `test_stale_data_branch` — stale data → check_freshness
- `test_unknown_escalation` — unknown → escalate_to_analyst
- `test_all_branches_coverage` — runs all 4 scenarios, proves all paths
- `test_state_transitions_recorded` — transitions in state_snapshot
- `test_deterministic_branching` — same input → same branch (3 runs)
- `test_budget_enforcement` — model_calls=1, iterations=2, tool_calls=0

## Common Failure Modes
- Missing fixture key → ScriptedModel falls back to default
- Classification returns no `incident_type` → defaults to `unknown`
- Branch functions are pure Python — no real failure modes

## Production-Hardening Requirements
- Replace ScriptedModel with real Gemini/Claude for classification
- Add persistent incident database for audit trail
- Add priority queue for human escalation tickets
- Add automated remediation playbooks for each branch
- Add time-series tracking of branch execution metrics
- Add rollback/undo capability for automated remediations

## Related Patterns
- `prompt-chaining` — sequential stages vs. conditional branches
- `routing` — model-driven vs. deterministic routing
- `evaluator-optimizer` — iterative feedback vs. one-shot branch

## Anti-Pattern Demonstrated or Avoided
- **Avoided:** Using model calls for deterministic routing decisions
- **Avoided:** Infinite or unbounded branching (bounded at 4 branches)
- **Avoided:** Mixed concerns (classification is the only model call)
- **Avoided:** Silent failure — unknown incidents always escalate
