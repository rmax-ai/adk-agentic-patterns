"""Pattern 06: Planner-Executor.

Scenario: Plan and execute a small conference setup using mocked venue, catering,
and calendar services.

Key design characteristics:
- Planner emits typed ExecutionPlan (list of tasks with dependencies, statuses)
- Executor cannot change the plan without a formal replan event
- Task dependencies enforced (task B can't start before task A completes)
- Task statuses: pending, in_progress, completed, failed
- Plan validation before execution (all task IDs unique, dependency graph acyclic)
- Replan after a simulated venue failure
- Maximum replan budget (1 replan allowed)
- Planner has no direct write tools — only read/plan
- Executor receives scoped tools for venue, catering, calendar
"""
from __future__ import annotations

import json
import sys
from collections import deque
from pathlib import Path
from typing import Any

# Ensure this example directory is on sys.path for absolute imports
_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))

from adk_patterns.config import Config
from adk_patterns.contracts import (
    ExecutionStatus,
    PatternRunResult,
    RunBudget,
    ToolInvocationRecord,
)
from adk_patterns.models import ScriptedModel
from adk_patterns.shared import RunContext, run_scope

from contracts import ExecutionPlan, Task, TaskStatus  # noqa: E402
from fixtures import FIXTURES  # noqa: E402
from mocks import MockCalendarService, MockCateringService, MockVenueService  # noqa: E402
from tools import TOOL_DEFINITIONS, create_executor_tools  # noqa: E402

# ---------------------------------------------------------------------------
# Shared mock service instances
# ---------------------------------------------------------------------------

_venue_service = MockVenueService()
_catering_service = MockCateringService()
_calendar_service = MockCalendarService()


# ---------------------------------------------------------------------------
# Plan validation
# ---------------------------------------------------------------------------


def validate_plan(plan: ExecutionPlan) -> tuple[bool, str | None]:
    """Validate an execution plan.

    Checks:
    1. All task IDs are unique
    2. All dependency references are valid (no missing deps)
    3. Dependency graph is acyclic (topological sort)

    Returns:
        (is_valid, error_message) tuple.
    """
    if not plan.tasks:
        return False, "Plan has no tasks"

    # Check unique IDs
    task_ids = [t.id for t in plan.tasks]
    if len(task_ids) != len(set(task_ids)):
        return False, "Duplicate task IDs found in plan"

    task_id_set = set(task_ids)

    # Check dependency references
    for task in plan.tasks:
        for dep_id in task.deps:
            if dep_id not in task_id_set:
                return False, f"Task '{task.id}' depends on unknown task '{dep_id}'"

    # Check for cycles via topological sort (Kahn's algorithm)
    in_degree: dict[str, int] = {t.id: 0 for t in plan.tasks}
    adjacency: dict[str, list[str]] = {t.id: [] for t in plan.tasks}

    for task in plan.tasks:
        for dep_id in task.deps:
            adjacency[dep_id].append(task.id)
            in_degree[task.id] = in_degree.get(task.id, 0) + 1

    queue = deque([tid for tid, deg in in_degree.items() if deg == 0])
    visited = 0

    while queue:
        node = queue.popleft()
        visited += 1
        for neighbor in adjacency.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if visited != len(plan.tasks):
        return False, "Dependency graph contains a cycle"

    return True, None


# ---------------------------------------------------------------------------
# Ready-task resolver
# ---------------------------------------------------------------------------


def _get_ready_tasks(plan: ExecutionPlan, task_results: dict[str, dict]) -> list[Task]:
    """Find tasks whose dependencies are all satisfied (completed).

    Args:
        plan: The execution plan.
        task_results: Dict of task_id -> result for completed tasks.

    Returns:
        List of tasks that are ready to execute (all deps completed).
    """
    ready: list[Task] = []
    for task in plan.tasks:
        if task.status != TaskStatus.PENDING:
            continue
        all_deps_done = all(
            dep_id in task_results for dep_id in task.deps
        )
        if all_deps_done:
            ready.append(task)
    return ready


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


def run_planner(
    ctx: RunContext,
    model: ScriptedModel,
    state: dict[str, Any],
    fixture_key: str,
) -> ExecutionPlan | None:
    """Invoke the planner to create or update an execution plan.

    The planner has ONLY read/plan capabilities — it accesses state
    (execution_plan, task_results) but has no write tools.

    Args:
        ctx: Run context.
        model: ScriptedModel with fixture responses.
        state: Current state dict (execution_plan, task_results, replan_count).
        fixture_key: Fixture key for deterministic response.

    Returns:
        An ExecutionPlan or None if the planner failed.
    """
    ctx.audit("planner", "model_call", resource="create_plan")
    ctx.record_model_call(tokens=150)

    planner_context = json.dumps(
        {
            "task_results": state.get("task_results", {}),
            "replan_count": state.get("replan_count", 0),
        },
        indent=2,
    )

    response = model.invoke(
        system_instruction=(
            "You are a conference planning assistant. Create a structured ExecutionPlan "
            "with a list of typed tasks (with IDs, names, dependencies, and tool mappings). "
            "Tasks must be ordered by dependency — a task can only depend on tasks listed "
            "before it. You have access to state information only; you cannot call tools directly."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"__FIXTURE__:{fixture_key} "
                    f"Plan the conference setup. Current state:\n{planner_context}"
                ),
            }
        ],
    )

    if response.structured_output:
        try:
            plan = ExecutionPlan(**response.structured_output)
            return plan
        except Exception as e:
            ctx.audit("planner", "parse_error", outcome="failure", metadata={"error": str(e)})
            ctx.mark_failed(f"Failed to parse plan from planner output: {e}")
            return None

    ctx.mark_failed("Planner returned no structured output")
    return None


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


def run_executor(
    ctx: RunContext,
    state: dict[str, Any],
    executor_tools: dict[str, Any],
) -> dict[str, Any]:
    """Execute tasks in the plan, respecting dependency ordering.

    The executor CANNOT change the plan — it only runs tasks from the
    existing plan and records results. If a task fails and triggers a
    replan, that is handled at the orchestration level.

    Args:
        ctx: Run context.
        state: Current state with 'execution_plan' and 'task_results'.
        executor_tools: Tool registry for the executor.

    Returns:
        Updated state dict with task_results.
    """
    plan: ExecutionPlan = state["execution_plan"]
    task_results: dict[str, dict] = dict(state.get("task_results", {}))
    # The executor loop is bounded by the number of tasks in the plan.
    # Each pass runs all currently-ready tasks in parallel (same batch).
    # We use a simple bound: at most N passes where N = number of tasks.
    max_passes = len(plan.tasks) * 2  # generous bound, prevents infinite loops
    iteration = 0

    while iteration < max_passes:
        iteration += 1

        ready_tasks = _get_ready_tasks(plan, task_results)
        if not ready_tasks:
            # No tasks ready — check if all done or some failed
            all_final = all(
                t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
                for t in plan.tasks
            )
            if all_final:
                break
            # There are pending tasks but none ready — dependency deadlock
            pending = [t.id for t in plan.tasks if t.status == TaskStatus.PENDING]
            ctx.audit(
                "executor",
                "deadlock",
                outcome="failure",
                metadata={"pending_unready": pending},
            )
            ctx.mark_failed(f"Deadlock: tasks {pending} are pending but none are ready")
            break

        # Execute each ready task (same dependency level)
        for task in ready_tasks:
            task.status = TaskStatus.IN_PROGRESS
            ctx.audit(
                "executor",
                "task_start",
                resource=task.id,
                metadata={"task_name": task.name, "tool": task.tool_name},
            )

            tool_result = _execute_single_task(ctx, executor_tools, task)
            task_results[task.id] = tool_result

            if tool_result.get("success") is False or "error" in tool_result:
                task.status = TaskStatus.FAILED
                ctx.audit(
                    "executor",
                    "task_failed",
                    resource=task.id,
                    outcome="failure",
                    metadata={"error": tool_result.get("error", "unknown")},
                )
            else:
                task.status = TaskStatus.COMPLETED
                ctx.audit(
                    "executor",
                    "task_completed",
                    resource=task.id,
                    outcome="success",
                    metadata={"result_summary": str(tool_result)[:200]},
                )

    state["task_results"] = task_results
    return state


def _execute_single_task(
    ctx: RunContext,
    executor_tools: dict[str, Any],
    task: Task,
) -> dict[str, Any]:
    """Execute a single task using the executor's scoped tools.

    Args:
        ctx: Run context.
        executor_tools: Tool registry.
        task: The task to execute.

    Returns:
        Tool call result dict.
    """
    tool_fn = executor_tools.get(task.tool_name)
    if tool_fn is None:
        error_msg = f"Tool '{task.tool_name}' is not available to the executor"
        ctx.audit("executor", "tool_unavailable", resource=task.tool_name, outcome="failure")
        ctx.record_tool_call(
            ToolInvocationRecord(
                tool_name=task.tool_name,
                validated_arguments=dict(task.tool_args),
                error_type="ToolUnavailableError",
            )
        )
        return {"error": error_msg}

    try:
        result = tool_fn(**task.tool_args)
        ctx.record_tool_call(
            ToolInvocationRecord(
                tool_name=task.tool_name,
                validated_arguments=dict(task.tool_args),
                result_summary=(
                    {"status": "success"}
                    if result.get("success") is not False
                    else {"status": "failed", "error": result.get("error", "unknown")}
                ),
            )
        )
        return dict(result)
    except Exception as e:
        ctx.record_tool_call(
            ToolInvocationRecord(
                tool_name=task.tool_name,
                validated_arguments=dict(task.tool_args),
                error_type=type(e).__name__,
            )
        )
        ctx.audit("executor", "tool_error", resource=task.tool_name, outcome="failure")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Replan logic
# ---------------------------------------------------------------------------


def _needs_replan(state: dict[str, Any]) -> bool:
    """Check if any task in the plan has failed and needs replanning.

    Args:
        state: Current state with execution_plan.

    Returns:
        True if any task has failed.
    """
    plan: ExecutionPlan = state.get("execution_plan")
    if not plan:
        return False
    return any(task.status == TaskStatus.FAILED for task in plan.tasks)


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


def _setup_executor_tools() -> dict[str, Any]:
    """Create and return the executor tool registry."""
    return create_executor_tools(_venue_service, _catering_service, _calendar_service)


def run_planner_executor(
    ctx: RunContext,
    model: ScriptedModel,
    fixture_key: str,
) -> dict[str, Any]:
    """Run the planner-executor pattern.

    Flow:
    1. Planner creates an ExecutionPlan (no write tools)
    2. Plan is validated (unique IDs, acyclic deps)
    3. Executor runs tasks in dependency order
    4. If a task fails, trigger replan (max 1 replan)
    5. Loop repeats from step 1 with budget check

    Args:
        ctx: Run context for audit and budget tracking.
        model: ScriptedModel with pre-configured fixtures.
        fixture_key: The test scenario fixture key.

    Returns:
        State dict with execution_plan, task_results, and replan_count.
    """
    state: dict[str, Any] = {
        "execution_plan": None,
        "task_results": {},
        "replan_count": 0,
    }
    executor_tools = _setup_executor_tools()

    max_planning_iterations = 3  # initial plan + up to 2 replans (budget-limit enforced)
    planning_iteration = 0

    while planning_iteration < max_planning_iterations:
        planning_iteration += 1
        ctx.record_iteration()

        # --- Step 1: Planner creates/updates the plan ---
        plan = run_planner(ctx, model, state, fixture_key)
        if plan is None:
            ctx.mark_failed("Planner failed to produce a valid plan")
            break

        # --- Step 2: Validate the plan ---
        is_valid, error_msg = validate_plan(plan)
        if not is_valid:
            ctx.audit(
                "orchestrator",
                "plan_validation_failed",
                outcome="failure",
                metadata={"error": error_msg},
            )
            # For plan_validation test, we should fail immediately
            if fixture_key == "plan_validation":
                ctx.mark_failed(f"Plan validation failed: {error_msg}")
                break
            ctx.mark_failed(f"Plan validation failed: {error_msg}")
            break

        ctx.audit(
            "orchestrator",
            "plan_validated",
            outcome="success",
            metadata={"task_count": len(plan.tasks)},
        )
        state["execution_plan"] = plan

        # --- Step 3: Executor runs tasks ---
        state = run_executor(ctx, state, executor_tools)

        # Check budget
        budget_status = ctx.check_budget()
        if budget_status:
            ctx.mark_budget_exhausted()
            break

        # --- Step 4: Check if replan needed ---
        if not _needs_replan(state):
            break  # All tasks completed successfully

        # Check replan budget
        max_replan = 1
        if state["replan_count"] >= max_replan:
            ctx.audit(
                "orchestrator",
                "replan_budget_exceeded",
                outcome="failure",
                metadata={"replan_count": state["replan_count"], "max_replan": max_replan},
            )
            ctx.mark_failed(f"Replan budget exceeded: {state['replan_count']}/{max_replan}")
            break

        # Trigger replan
        state["replan_count"] += 1
        ctx.audit(
            "orchestrator",
            "replan",
            outcome="success",
            metadata={"replan_count": state["replan_count"]},
        )
        # Reset task statuses for the new plan
        if state.get("execution_plan"):
            for task in state["execution_plan"].tasks:
                if task.status != TaskStatus.COMPLETED:
                    task.status = TaskStatus.PENDING

    ctx.snapshot_state(state)
    return state


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def run(config: Config | None = None, scenario: str = "default") -> PatternRunResult:
    """Entry point for CLI and tests.

    Args:
        config: Application configuration (uses defaults if None).
        scenario: Test scenario key.

    Returns:
        A PatternRunResult with status, output, metrics, and audit trail.
    """
    model = ScriptedModel()

    fixture_seq = FIXTURES.get(scenario)
    if fixture_seq:
        model.set_response_sequence(fixture_seq)

    budget = RunBudget(max_model_calls=5, max_tool_calls=10, max_iterations=3)

    with run_scope(
        "planner-executor",
        scenario,
        max_model_calls=budget.max_model_calls,
        max_tool_calls=budget.max_tool_calls,
        max_iterations=budget.max_iterations,
    ) as ctx:
        # Reset mock services for each run
        _venue_service.venues["venue-001"]["available"] = True
        _venue_service.bookings.clear()
        _catering_service.orders.clear()
        _calendar_service.events.clear()

        state = run_planner_executor(ctx, model, scenario)
        ctx.output = state

    return ctx.to_result()


def main(config: Config | None = None, scenario: str = "default") -> PatternRunResult:
    """Standard entry point called by CLI."""
    return run(config=config, scenario=scenario)
