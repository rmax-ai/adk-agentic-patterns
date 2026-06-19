"""Pattern 10: Supervisor-Worker.

Scenario: Supervisor decomposes a product-launch review into specialist
worker tasks, maintains a typed task ledger, enforces bounded delegation
depth (1), prevents cross-worker task modification, and produces a final
synthesis only after all required tasks complete.

Key design characteristics:
- Supervisor creates typed task ledger via ScriptedModel fixture
- Worker registry with explicit assignment records
- Workers cannot modify tasks assigned to other workers
- Workers cannot spawn sub-workers (bounded delegation depth = 1)
- No recursive spawning
- Final synthesis only after all required tasks complete
- Budget enforcement: max_model_calls=6, max_tool_calls=10
"""

from __future__ import annotations

import sys
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

from contracts import SynthesisResult, Task, TaskLedger, TaskStatus, WorkerRegistration  # noqa: E402
from fixtures import FIXTURES  # noqa: E402
from mocks import MockComplianceWorker, MockLaunchWorker, MockMarketWorker, MockTechWorker  # noqa: E402
from tools import (  # noqa: E402
    WORKER_TOOL_ALLOWLIST,
    TASK_ASSIGNMENTS,
    check_worker_tool_allowed,
    check_worker_can_modify_task,
    create_worker_tools,
    update_task_assignment,
    clear_assignments,
)

# ---------------------------------------------------------------------------
# Shared mock service instances
# ---------------------------------------------------------------------------

_market_worker = MockMarketWorker()
_tech_worker = MockTechWorker()
_compliance_worker = MockComplianceWorker()
_launch_worker = MockLaunchWorker()


# ---------------------------------------------------------------------------
# Supervisor: decompose into tasks
# ---------------------------------------------------------------------------


def run_supervisor(
    ctx: RunContext,
    model: ScriptedModel,
    fixture_key: str,
) -> tuple[TaskLedger | None, list[WorkerRegistration] | None]:
    """Invoke the supervisor model to decompose a product-launch review.

    The supervisor produces a TaskLedger (list of tasks with assignments)
    and a WorkerRegistry (list of worker registrations with capabilities).

    Args:
        ctx: Run context.
        model: ScriptedModel with fixture responses.
        fixture_key: Fixture key for deterministic response.

    Returns:
        Tuple of (TaskLedger, list of WorkerRegistration) or (None, None) on failure.
    """
    ctx.audit("supervisor", "model_call", resource="decompose_tasks")
    ctx.record_model_call(tokens=150)

    response = model.invoke(
        system_instruction=(
            "You are a product-launch review supervisor. Decompose the review "
            "into specialist tasks and assign them to registered workers. "
            "Return a structured response with:\n"
            "- 'task_ledger': dict with 'tasks' list (each task has id, name, assignee, status, result)\n"
            "- 'worker_registry': list of worker registrations (each has id, capabilities[])\n"
            "Tasks must have unique IDs. Workers can only be assigned to tasks "
            "that match their capabilities."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"__FIXTURE__:{fixture_key} "
                    "Decompose the product-launch review for Product X into specialist tasks. "
                    "Assign each task to the appropriate worker based on capabilities."
                ),
            }
        ],
    )

    if response.structured_output:
        try:
            output = response.structured_output
            ledger_data = output.get("task_ledger", {})
            worker_data = output.get("worker_registry", [])

            task_ledger = TaskLedger(**ledger_data)
            workers = [WorkerRegistration(**w) for w in worker_data]

            ctx.audit(
                "supervisor",
                "decomposition_complete",
                outcome="success",
                metadata={
                    "task_count": len(task_ledger.tasks),
                    "worker_count": len(workers),
                    "task_ids": [t.id for t in task_ledger.tasks],
                },
            )

            # Register task assignments in the global tracking dict
            for task in task_ledger.tasks:
                update_task_assignment(task.id, task.assignee)

            return task_ledger, workers
        except Exception as e:
            ctx.audit(
                "supervisor",
                "parse_error",
                outcome="failure",
                metadata={"error": str(e)},
            )
            ctx.mark_failed(f"Failed to parse supervisor output: {e}")
            return None, None

    ctx.mark_failed("Supervisor returned no structured output")
    return None, None


# ---------------------------------------------------------------------------
# Worker execution
# ---------------------------------------------------------------------------


def run_worker(
    ctx: RunContext,
    worker_id: str,
    task: Task,
    worker_tools: dict[str, Any],
) -> Task:
    """Execute a single task on behalf of a worker.

    The worker can only use tools allowed in their allowlist and can only
    modify tasks assigned to them.

    Args:
        ctx: Run context.
        worker_id: The worker executing the task.
        task: The task to execute.
        worker_tools: Tool registry for this worker.

    Returns:
        Updated Task with result populated.
    """
    # Validate this worker is allowed to modify this task
    if not check_worker_can_modify_task(worker_id, task.id):
        ctx.audit(
            "worker",
            "permission_denied",
            resource=task.id,
            outcome="failure",
            metadata={
                "worker_id": worker_id,
                "task_assignee": task.assignee,
                "reason": "worker_cannot_modify_unassigned_task",
            },
        )
        task.status = TaskStatus.FAILED
        task.result = {
            "error": f"Worker '{worker_id}' is not assigned to task '{task.id}'",
            "reason": "cross_worker_modification_blocked",
        }
        return task

    # Determine which tool to call based on task name/capability matching
    task_name_lower = task.name.lower()

    # Map task names to tool names
    tool_map: dict[str, str] = {
        "market analysis": "market_analyze",
        "technical review": "tech_review",
        "compliance check": "compliance_check",
        "launch readiness": "assess_readiness",
    }

    tool_name = tool_map.get(task_name_lower)
    if tool_name is None:
        # Fallback: try to find by task id
        task_id_tool_map: dict[str, str] = {
            "task-market": "market_analyze",
            "task-tech": "tech_review",
            "task-compliance": "compliance_check",
            "task-launch": "assess_readiness",
        }
        tool_name = task_id_tool_map.get(task.id)

    if tool_name is None:
        ctx.audit(
            "worker",
            "no_tool_for_task",
            resource=task.id,
            outcome="failure",
            metadata={"task_name": task.name, "worker_id": worker_id},
        )
        task.status = TaskStatus.FAILED
        task.result = {"error": f"No matching tool found for task '{task.name}'"}
        return task

    # Validate worker is allowed to use this tool
    if not check_worker_tool_allowed(worker_id, tool_name):
        ctx.audit(
            "worker",
            "tool_permission_denied",
            resource=tool_name,
            outcome="failure",
            metadata={
                "worker_id": worker_id,
                "tool_name": tool_name,
                "reason": "tool_not_in_worker_allowlist",
            },
        )
        task.status = TaskStatus.FAILED
        task.result = {
            "error": f"Worker '{worker_id}' is not allowed to use tool '{tool_name}'",
        }
        return task

    # Execute the tool
    tool_fn = worker_tools.get(tool_name)
    if tool_fn is None:
        ctx.audit(
            "worker",
            "tool_unavailable",
            resource=tool_name,
            outcome="failure",
            metadata={"worker_id": worker_id},
        )
        task.status = TaskStatus.FAILED
        task.result = {"error": f"Tool '{tool_name}' is not available"}
        return task

    ctx.audit(
        "worker",
        "task_start",
        resource=task.id,
        metadata={"worker_id": worker_id, "tool_name": tool_name, "task_name": task.name},
    )

    task.status = TaskStatus.IN_PROGRESS

    try:
        # Determine arguments based on tool
        if tool_name in ("compliance_check",):
            result = tool_fn(product="Product X", region="global")
        elif tool_name == "pricing_review":
            result = tool_fn(product="Product X", price=99.99)
        else:
            result = tool_fn(product="Product X")

        ctx.record_tool_call(
            ToolInvocationRecord(
                tool_name=tool_name,
                validated_arguments={"product": "Product X", "worker_id": worker_id},
                result_summary=dict(result) if isinstance(result, dict) else {"result": str(result)},
            )
        )

        task.status = TaskStatus.COMPLETED
        task.result = dict(result)

        ctx.audit(
            "worker",
            "task_completed",
            resource=task.id,
            outcome="success",
            metadata={"worker_id": worker_id, "result_summary": str(result)[:200]},
        )
    except Exception as e:
        ctx.record_tool_call(
            ToolInvocationRecord(
                tool_name=tool_name,
                validated_arguments={"product": "Product X", "worker_id": worker_id},
                error_type=type(e).__name__,
            )
        )
        task.status = TaskStatus.FAILED
        task.result = {"error": str(e)}
        ctx.audit(
            "worker",
            "task_failed",
            resource=task.id,
            outcome="failure",
            metadata={"worker_id": worker_id, "error": str(e)},
        )

    return task


# ---------------------------------------------------------------------------
# Bounded delegation guard
# ---------------------------------------------------------------------------


def check_delegation_depth(task: Task | None, current_depth: int) -> bool:
    """Enforce bounded delegation depth.

    Workers CANNOT spawn sub-workers (depth > 1 is rejected).

    Args:
        task: The task being delegated (unused, for interface consistency).
        current_depth: Current delegation depth.

    Returns:
        True if delegation is allowed (depth <= 1), False otherwise.
    """
    # Bounded delegation: max depth = 1 (supervisor -> worker only)
    return current_depth <= 1


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------


def run_synthesis(
    ctx: RunContext,
    task_ledger: TaskLedger,
) -> SynthesisResult:
    """Produce a final synthesis summary after all tasks complete.

    Args:
        ctx: Run context.
        task_ledger: The completed task ledger.

    Returns:
        SynthesisResult with summary, conclusions, and status.
    """
    ctx.audit("supervisor", "synthesis_start", resource="product_launch_review")

    conclusions: dict[str, Any] = {}
    for task in task_ledger.tasks:
        conclusions[task.id] = {
            "task_name": task.name,
            "assignee": task.assignee,
            "status": task.status.value,
            "result_summary": str(task.result)[:300] if task.result else "none",
        }

    completed_count = sum(1 for t in task_ledger.tasks if t.status == TaskStatus.COMPLETED)
    failed_count = sum(1 for t in task_ledger.tasks if t.status == TaskStatus.FAILED)

    if failed_count > 0:
        overall_status = "partial"
        summary = (
            f"Product-launch review completed with {completed_count}/{len(task_ledger.tasks)} "
            f"tasks successful and {failed_count} tasks failed. "
            f"Review requires attention on failed items before proceeding."
        )
    else:
        overall_status = "completed"
        summary = (
            f"Product-launch review completed successfully. "
            f"All {completed_count} tasks completed with positive results. "
            f"Recommendation: proceed with launch."
        )

    result = SynthesisResult(
        summary=summary,
        task_count=len(task_ledger.tasks),
        conclusions=conclusions,
        status=overall_status,
    )

    ctx.audit(
        "supervisor",
        "synthesis_complete",
        outcome="success",
        metadata={
            "completed_count": completed_count,
            "failed_count": failed_count,
            "status": overall_status,
        },
    )

    return result


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


def _setup_worker_tools() -> dict[str, dict[str, Any]]:
    """Create scoped tool registries for all workers."""
    return create_worker_tools(
        _market_worker,
        _tech_worker,
        _compliance_worker,
        _launch_worker,
    )


def run_supervisor_worker(
    ctx: RunContext,
    model: ScriptedModel,
    fixture_key: str,
) -> dict[str, Any]:
    """Run the supervisor-worker pattern.

    Flow:
    1. Supervisor decomposes product-launch review into typed tasks
    2. Each worker executes its assigned task
    3. Cross-worker modification is prevented via permission checks
    4. Bounded delegation depth is enforced
    5. Final synthesis only after all required tasks complete

    Args:
        ctx: Run context for audit and budget tracking.
        model: ScriptedModel with pre-configured fixtures.
        fixture_key: The test scenario fixture key.

    Returns:
        State dict with task_ledger, worker_registry, and synthesis.
    """
    state: dict[str, Any] = {
        "task_ledger": {},
        "worker_registry": [],
        "synthesis": None,
    }

    # Clear any stale task assignments
    clear_assignments()

    # --- Step 1: Supervisor decomposes ---
    ctx.audit("supervisor", "decomposition_start")
    task_ledger, workers = run_supervisor(ctx, model, fixture_key)

    if task_ledger is None or workers is None:
        ctx.mark_failed("Supervisor failed to produce a valid task ledger")
        return state

    state["task_ledger"] = task_ledger.model_dump()
    state["worker_registry"] = [w.model_dump() for w in workers]

    # Check budget after supervisor model call
    budget_status = ctx.check_budget()
    if budget_status:
        ctx.mark_budget_exhausted()
        return state

    # --- Step 2: Workers execute tasks ---
    all_worker_tools = _setup_worker_tools()
    delegation_depth = 1  # Supervisor->Worker = depth 1 (max allowed)

    # Check bounded delegation
    if not check_delegation_depth(None, delegation_depth):
        ctx.mark_failed("Delegation depth exceeded maximum (1)")
        return state

    for task in task_ledger.tasks:
        # Check budget before each task
        budget_status = ctx.check_budget()
        if budget_status:
            ctx.mark_budget_exhausted()
            break

        worker_id = task.assignee
        worker_tools = all_worker_tools.get(worker_id, {})

        if not worker_tools:
            ctx.audit(
                "supervisor",
                "worker_not_found",
                resource=worker_id,
                outcome="failure",
                metadata={"task_id": task.id},
            )
            task.status = TaskStatus.FAILED
            task.result = {"error": f"Worker '{worker_id}' not found in registry"}
            continue

        # Execute the task
        task = run_worker(ctx, worker_id, task, worker_tools)

        # --- Step 3: Enforce no recursive spawning ---
        # Workers cannot spawn sub-workers. If any task's result indicates
        # a sub-delegation attempt, we block it.
        result_str = str(task.result).lower()
        if "sub_worker" in result_str or "sub-worker" in result_str or "delegate" in result_str:
            ctx.audit(
                "supervisor",
                "recursive_spawn_blocked",
                resource=task.id,
                outcome="failure",
                metadata={
                    "worker_id": worker_id,
                    "reason": "workers_cannot_spawn_sub_workers",
                },
            )
            task.status = TaskStatus.FAILED
            task.result = {
                "error": "Recursive spawning blocked: workers cannot spawn sub-workers",
                "reason": "bounded_delegation_enforced",
            }

        # Check budget after each worker tool call
        budget_status = ctx.check_budget()
        if budget_status:
            ctx.mark_budget_exhausted()
            break

    # Update the state with modified tasks
    state["task_ledger"] = task_ledger.model_dump()

    # --- Step 4: Synthesis (only after all tasks complete) ---
    all_completed = all(
        t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
        for t in task_ledger.tasks
    )

    if all_completed:
        synthesis = run_synthesis(ctx, task_ledger)
        state["synthesis"] = synthesis.model_dump()
    else:
        pending_tasks = [t.id for t in task_ledger.tasks if t.status == TaskStatus.PENDING]
        ctx.audit(
            "supervisor",
            "synthesis_deferred",
            outcome="pending",
            metadata={"pending_tasks": pending_tasks},
        )
        state["synthesis"] = {
            "summary": "Synthesis deferred — not all tasks completed",
            "task_count": len(task_ledger.tasks),
            "conclusions": {},
            "status": "deferred",
        }

    ctx.snapshot_state(state)
    return state


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def run(
    config: Config | None = None,
    scenario: str = "default",
) -> PatternRunResult:
    """Entry point for CLI and tests.

    Args:
        config: Application configuration (uses defaults if None).
        scenario: Test scenario key.

    Returns:
        PatternRunResult with task_ledger, worker_registry, and synthesis.
    """
    model = ScriptedModel()

    # Register fixture sequences
    for key, seq in FIXTURES.items():
        if scenario == key:
            model.set_response_sequence(seq)
            break
    else:
        # Default to standard fixture
        model.set_response_sequence(FIXTURES.get("standard", []))

    fixture_key = scenario if scenario in FIXTURES else "standard"

    with run_scope(
        "supervisor-worker",
        scenario,
        max_model_calls=6,
        max_tool_calls=10,
        max_iterations=5,
    ) as ctx:
        state = run_supervisor_worker(ctx, model, fixture_key)
        ctx.output = state
        ctx.snapshot_state(state)

    return ctx.to_result()


def main(config: Config | None = None, scenario: str = "default") -> PatternRunResult:
    """Standard entry point called by CLI."""
    return run(config=config, scenario=scenario)
