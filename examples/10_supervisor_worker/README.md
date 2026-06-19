# Pattern 10: Supervisor-Worker

## Problem
Supervisor decomposes a product-launch review into specialist tasks, each handled by a dedicated worker, with final synthesis only after all tasks complete.

## Pattern
A two-tier delegation pattern:
1. **Supervisor** — Decomposes the product-launch review into typed tasks, assigns them to registered workers, and produces a final synthesis
2. **Workers** — Execute their assigned tasks using scoped, isolated tools; cannot modify tasks belonging to other workers; cannot spawn sub-workers

## Why This Pattern Is Justified
- Separates decomposition (supervisor) from execution (worker)
- Typed task ledger ensures accountability and auditability
- Cross-worker modification prevention isolates failures
- Bounded delegation depth (1) prevents runaway delegation chains
- Final synthesis consolidates results only after all tasks complete

## Simpler Alternative
Single agent handles everything — but with no separation of concerns, no isolation, and no bounded delegation.

## ADK Primitives Used
- `ScriptedModel` (offline fake model for deterministic testing)
- `structured_response` (fixture-based model responses)
- `RunContext` (budget tracking, audit events, state snapshots)

## Information Flow
```
Product-Launch Request → Supervisor → TaskLedger (typed tasks)
                                          ↓
                              Worker Registry (assignments)
                                          ↓
                         Worker A → Task A → Result A
                         Worker B → Task B → Result B
                         Worker C → Task C → Result C
                                          ↓
                              Supervisor → Synthesis
```

## Control Flow
```
1. Supervisor receives product-launch review request
2. Supervisor decomposes into typed tasks with worker assignments
3. Each worker executes its assigned task with scoped tools
4. Cross-worker modification is enforced (Worker B cannot modify Task A)
5. Delegation depth is bounded to 1 (no worker can spawn sub-workers)
6. Final synthesis produced only after all tasks complete
```

## State Model
- Transient state per request — no persistent storage
- State keys: `task_ledger`, `worker_registry`, `synthesis`

## State Ownership Table

- **task_ledger** — Writer: Supervisor, Readers: Workers, Scope: Per-request
- **worker_registry** — Writer: Supervisor, Readers: Workers (own entry only), Scope: Per-request
- **synthesis** — Writer: Supervisor, Readers: Output, Scope: Per-request

## Worker Permission Table

- **worker_market** — Tools: market_analyze, pricing_review, competitor_intel — Tasks: task-market
- **worker_tech** — Tools: tech_review, security_audit, performance_benchmark — Tasks: task-tech
- **worker_compliance** — Tools: compliance_check, regulatory_review, data_privacy — Tasks: task-compliance
- **worker_launch** — Tools: assess_readiness, go_to_market — Tasks: task-launch

## Success Termination
Supervisor creates tasks → all workers complete assignments → synthesis produced.

## Failure Termination
- Supervisor fails to produce valid task ledger
- Worker tries to modify another worker's task (permission denied)
- Worker tries to spawn sub-worker (bounded delegation depth)
- Budget exhausted

## Retry Policy
No retry — single-pass decomposition and execution.

## Execution Budgets
- max_model_calls: 6
- max_tool_calls: 10
- max_iterations: 5

## How to Run Offline
```bash
uv run python -m examples.10_supervisor_worker.run
uv run python -m examples.10_supervisor_worker.run standard
uv run pytest examples/10_supervisor_worker/test_example.py -v
```

## How to Run with Gemini
```bash
PATTERNS_EXECUTION_MODE=live GOOGLE_API_KEY=... uv run python -m examples.10_supervisor_worker.run
```

## Expected Output
See `expected/success.json` — standard product-launch review with task ledger and synthesis.
See `expected/failure.json` — bounded delegation failure when depth exceeded.

## Tests Included
- `test_supervisor_decomposes` — creates 3-4 tasks with worker assignments
- `test_workers_execute` — each worker completes assigned task
- `test_workers_cannot_modify_others` — worker B blocked from modifying Task A
- `test_synthesis_after_completion` — final summary only after all tasks done
- `test_bounded_delegation` — no worker can spawn sub-workers
- `test_no_recursive_spawning`

## Common Failure Modes
- Worker assigned to task with mismatched capabilities → task fails
- Worker attempts to modify another worker's task → permission denied
- Worker attempts to spawn sub-worker → bounded delegation blocks it
- Budget exhausted mid-execution

## Production-Hardening Requirements
- Replace scripted model with real Gemini/Claude
- Add persistent task ledger storage
- Add worker health checks and timeout monitoring
- Add telemetry export (OpenTelemetry collector)
- Add supervisor fallback (alternative decomposition strategy)

## Related Patterns
- `router-specialist` — simpler routing without task delegation
- `planner-executor` — plan execution with dependency ordering
- `parallel-fanout-gather` — fan-out to parallel workers

## Anti-Pattern Demonstrated or Avoided
- **Avoided:** Workers modifying tasks they don't own (cross-worker isolation)
- **Avoided:** Unbounded delegation chains (bounded depth = 1)
- **Avoided:** Recursive spawning (blocked at enforcement layer)
- **Avoided:** Synthesis before all tasks complete (deferred until done)
