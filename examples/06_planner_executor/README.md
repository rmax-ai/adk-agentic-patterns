# Pattern 06: Planner-Executor

## Problem
Set up a conference (venue, catering, calendar) where the AI must first create a plan and then execute it step by step — with the ability to re-plan when things go wrong.

## Pattern
Two distinct roles:
- **Planner**: Creates/updates an `ExecutionPlan` (list of typed tasks with dependencies). Has **no write tools** — only reads state and produces plans.
- **Executor**: Runs tasks from the plan using scoped tools (venue, catering, calendar). Cannot change the plan without a formal replan event.

Task dependencies are enforced (task B can't start before task A completes), and plan validation checks for duplicate IDs and cyclic graphs before execution.

## Why This Pattern Is Justified
- Separates planning from execution for auditability and safety
- Planner can focus on strategy without side effects
- Executor can focus on reliable task execution
- Replan capability handles real-world failures gracefully
- Dependency enforcement prevents race conditions

## Simpler Alternative
Single agent with all tools — but it conflates planning and execution, making debugging harder and increasing the risk of side effects during planning.

## ADK Primitives Used
- `ScriptedModel` (offline deterministic model)
- `structured_response` (typed structured outputs)
- `RunContext` (audit trail, budget tracking)

## Information Flow
```
User Request → Planner → ExecutionPlan (typed) → Validator → Executor → Task Results
                    ↑                                               │
                    └─── Replan (on failure, max 1 attempt) ←───────┘
```

## Control Flow
```
1. Planner reads state (task_results, replan_count)
2. Planner emits typed ExecutionPlan
3. Plan validated (unique IDs, acyclic deps)
4. Executor runs ready tasks in dependency order
5. If task fails → notify planner for replan (max 1)
6. Repeat from step 1 or exit on success
```

## State Model

### State Keys
| Key | Writer | Readers | Scope |
|-----|--------|---------|-------|
| `execution_plan` | Planner | Executor | Per run |
| `task_results{}` | Executor | Planner, Executor | Per run |
| `replan_count` | Orchestrator | Planner | Per run |

## Tool Permission Table

### Planner (read-only — no write tools)
| Tool | Agent | Permissions |
|------|-------|-------------|
| state access | Planner | read-only (execution_plan, task_results) |
| model call | Planner | emit typed ExecutionPlan |

### Executor (scoped write tools)
| Tool | Agent | Permissions |
|------|-------|-------------|
| `check_availability` | Executor | read venue data |
| `book_venue` | Executor | write booking |
| `cancel_venue` | Executor | write cancellation |
| `order_catering` | Executor | write catering order |
| `schedule_event` | Executor | write calendar event |

## Success Termination
All tasks in the execution plan reach `completed` status.

## Failure Termination
- Plan validation fails (duplicate IDs, cyclic deps)
- Replan budget exceeded (max 1 replan)
- Task dependency deadlock
- Planner fails to produce valid plan

## Retry Policy
No retry for individual tasks — failure triggers a full replan from the planner (max 1 replan).

## Execution Budgets
- max_model_calls: 5
- max_tool_calls: 10
- max_iterations: 3

## How to Run Offline
```bash
uv run python -m examples.06_planner_executor.run
uv run python -m examples.06_planner_executor.run plan_and_execute
uv run pytest examples/06_planner_executor/test_example.py -v
```

## How to Run with Gemini
```bash
PATTERNS_EXECUTION_MODE=live GOOGLE_API_KEY=... uv run python -m examples.06_planner_executor.run
```

## Expected Output
See `expected/success.json` — plan with task results and execution metrics.

## Tests Included
- `test_plan_and_execute` — full plan-and-execute cycle
- `test_replan_after_failure` — venue failure triggers replan
- `test_plan_validation` — invalid plan rejected
- `test_planner_no_write_tools` — planner cannot call executor tools
- `test_max_replan_budget` — second replan fails
- `test_task_dependency_order` — tasks respect dependencies

## Common Failure Modes
- **Cyclic dependencies** → Plan validation fails
- **Duplicate task IDs** → Plan validation fails
- **Venue unavailable** → Replan triggered (max 1 attempt)
- **Planner uses write tool** → Not possible — tools not passed to planner

## Production-Hardening Requirements
- Replace ScriptedModel with real LLM (Gemini/Claude)
- Add persistent plan storage
- Add human-in-the-loop for replan approval
- Add rollback/saga pattern for failed plan execution
- Add timeout per individual task

## Related Patterns
- `tool-using-agent` — when planning not needed
- `evaluator-optimizer` — when iterative improvement needed instead of replan
- `sequential-specialists` — when plan is fixed at design time

## Anti-Pattern Demonstrated or Avoided
- **Avoided:** Planner directly executing side effects (write tools)
- **Demonstrated:** Explicit replan boundary enforces separation of concerns
