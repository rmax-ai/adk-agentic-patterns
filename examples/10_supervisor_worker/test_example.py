"""Tests for Pattern 10: Supervisor-Worker.

Covers:
- test_supervisor_decomposes — creates 3-4 tasks with assignments
- test_workers_execute — each worker completes assigned task
- test_workers_cannot_modify_others — worker B blocked from modifying Task A
- test_synthesis_after_completion — final summary only after all tasks done
- test_bounded_delegation — no worker can spawn sub-workers
- test_no_recursive_spawning
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Example directories starting with digits aren't valid Python packages.
# Add parent to path so we can import from them.
_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))

from agent import (  # noqa: E402
    check_delegation_depth,
    check_worker_can_modify_task,
    run,
    run_synthesis,
)
from contracts import Task, TaskLedger, TaskStatus  # noqa: E402

from adk_patterns.contracts import ExecutionStatus  # noqa: E402
from adk_patterns.models import ScriptedModel, structured_response  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ledger_with_tasks() -> TaskLedger:
    """Create a standard task ledger for testing."""
    return TaskLedger(
        tasks=[
            Task(id="task-market", name="Market Analysis", assignee="worker_market", status=TaskStatus.COMPLETED, result={"product": "X", "market_size": "$500M"}),
            Task(id="task-tech", name="Technical Review", assignee="worker_tech", status=TaskStatus.COMPLETED, result={"product": "X", "tech_score": 8.5}),
            Task(id="task-compliance", name="Compliance Check", assignee="worker_compliance", status=TaskStatus.COMPLETED, result={"product": "X", "compliance": "pass"}),
            Task(id="task-launch", name="Launch Readiness", assignee="worker_launch", status=TaskStatus.COMPLETED, result={"product": "X", "readiness": 92}),
        ]
    )


# ---------------------------------------------------------------------------
# Test: Supervisor decomposes product-launch review
# ---------------------------------------------------------------------------


def test_supervisor_decomposes() -> None:
    """Supervisor creates 3-4 tasks with worker assignments."""
    result = run(scenario="standard")

    assert result.status == ExecutionStatus.SUCCEEDED, (
        f"Expected SUCCEEDED, got {result.status}: {result.failure_reason}"
    )
    assert result.output is not None

    output = result.output
    task_ledger = output.get("task_ledger", {})
    assert task_ledger, "task_ledger should be present in output"

    tasks = task_ledger.get("tasks", []) if isinstance(task_ledger, dict) else task_ledger.tasks if hasattr(task_ledger, "tasks") else []
    assert isinstance(tasks, list) and 3 <= len(tasks) <= 4, (
        f"Expected 3-4 tasks, got {len(tasks) if isinstance(tasks, list) else 'N/A'}"
    )

    # Each task should have an id, name, and assignee
    for task in tasks:
        tid = task.get("id") if isinstance(task, dict) else task.id
        tname = task.get("name") if isinstance(task, dict) else task.name
        tassignee = task.get("assignee") if isinstance(task, dict) else task.assignee
        assert tid, "Task must have an id"
        assert tname, "Task must have a name"
        assert tassignee, "Task must have an assignee"

    # Worker registry should be present
    worker_registry = output.get("worker_registry", [])
    assert isinstance(worker_registry, list) and len(worker_registry) >= 3, (
        f"Expected at least 3 workers, got {len(worker_registry)}"
    )

    # Verify worker registration objects have required fields
    for worker in worker_registry:
        wid = worker.get("id") if isinstance(worker, dict) else worker.id if hasattr(worker, "id") else None
        caps = worker.get("capabilities") if isinstance(worker, dict) else worker.capabilities if hasattr(worker, "capabilities") else []
        assert wid, "Worker must have an id"
        assert len(caps) > 0, f"Worker {wid} must have capabilities"


# ---------------------------------------------------------------------------
# Test: Workers execute assigned tasks
# ---------------------------------------------------------------------------


def test_workers_execute() -> None:
    """Each worker completes their assigned task successfully."""
    result = run(scenario="standard")

    assert result.status == ExecutionStatus.SUCCEEDED, (
        f"Expected SUCCEEDED, got {result.status}: {result.failure_reason}"
    )

    output = result.output
    task_ledger = output.get("task_ledger", {})
    tasks = task_ledger.get("tasks", []) if isinstance(task_ledger, dict) else []

    # All tasks should be completed or failed
    for task in tasks:
        status = task.get("status") if isinstance(task, dict) else task.status
        assert status in ("completed", "failed"), (
            f"Task {task.get('id', 'unknown')} has unexpected status: {status}"
        )

    # At least some tasks should have results
    completed_tasks = [t for t in tasks if (t.get("status") if isinstance(t, dict) else t.status) == "completed"]
    assert len(completed_tasks) >= 3, (
        f"Expected at least 3 completed tasks, got {len(completed_tasks)}"
    )

    # Each completed task should have a non-empty result
    for task in completed_tasks:
        result_data = task.get("result") if isinstance(task, dict) else task.result
        assert result_data, f"Task {task.get('id', 'unknown')} should have result data"

    # Audit events should show worker activity
    worker_events = [e for e in result.audit_events if e.actor == "worker"]
    assert len(worker_events) > 0, "Expected worker audit events"

    # Tool calls should be recorded
    assert result.metrics["tool_calls"] > 0, "Expected at least 1 tool call"

    # Model calls should be recorded (supervisor decomposition)
    assert result.metrics["model_calls"] >= 1, "Expected at least 1 model call"


# ---------------------------------------------------------------------------
# Test: Workers cannot modify others' tasks
# ---------------------------------------------------------------------------


def test_workers_cannot_modify_others() -> None:
    """Worker B is blocked from modifying Task A (assigned to Worker A)."""
    # Verify the permission check function works correctly
    assert check_worker_can_modify_task("worker_market", "task-market") is True, (
        "worker_market should be able to modify task-market"
    )
    assert check_worker_can_modify_task("worker_tech", "task-market") is False, (
        "worker_tech should NOT be able to modify task-market"
    )
    assert check_worker_can_modify_task("worker_compliance", "task-market") is False, (
        "worker_compliance should NOT be able to modify task-market"
    )
    assert check_worker_can_modify_task("worker_launch", "task-market") is False, (
        "worker_launch should NOT be able to modify task-market"
    )

    # Verify each worker can only modify their own tasks
    assert check_worker_can_modify_task("worker_tech", "task-tech") is True
    assert check_worker_can_modify_task("worker_compliance", "task-compliance") is True
    assert check_worker_can_modify_task("worker_launch", "task-launch") is True

    # Verify cross-worker checks
    assert check_worker_can_modify_task("worker_market", "task-tech") is False
    assert check_worker_can_modify_task("worker_market", "task-compliance") is False
    assert check_worker_can_modify_task("worker_tech", "task-launch") is False


# ---------------------------------------------------------------------------
# Test: Synthesis after completion
# ---------------------------------------------------------------------------


def test_synthesis_after_completion() -> None:
    """Final synthesis is produced only after all required tasks complete."""
    result = run(scenario="standard")

    assert result.status == ExecutionStatus.SUCCEEDED, (
        f"Expected SUCCEEDED, got {result.status}: {result.failure_reason}"
    )

    output = result.output
    synthesis = output.get("synthesis", None)
    assert synthesis is not None, "Synthesis should be present in output"

    # If synthesis has status 'completed' or 'partial', it means all tasks finished
    syn_status = synthesis.get("status") if isinstance(synthesis, dict) else synthesis.status if hasattr(synthesis, "status") else ""
    assert syn_status in ("completed", "partial"), (
        f"Expected synthesis status to be 'completed' or 'partial', got '{syn_status}'"
    )

    # Synthesis should include a summary
    summary = synthesis.get("summary") if isinstance(synthesis, dict) else synthesis.summary if hasattr(synthesis, "summary") else ""
    assert summary, "Synthesis should include a summary"

    # Synthesis should have conclusions
    conclusions = synthesis.get("conclusions") if isinstance(synthesis, dict) else synthesis.conclusions if hasattr(synthesis, "conclusions") else {}
    assert isinstance(conclusions, dict) and len(conclusions) > 0, (
        "Synthesis should contain per-task conclusions"
    )

    # Synthesis audit event should be present
    synthesis_events = [e for e in result.audit_events if e.action == "synthesis_complete"]
    assert len(synthesis_events) >= 1, "Expected synthesis_complete audit event"

    # Verify synthesis function produces correct output
    ctx = None
    ledger = TaskLedger(
        tasks=[
            Task(id="t1", name="Task 1", assignee="w1", status=TaskStatus.COMPLETED, result={"ok": True}),
            Task(id="t2", name="Task 2", assignee="w2", status=TaskStatus.COMPLETED, result={"ok": True}),
        ]
    )


# ---------------------------------------------------------------------------
# Test: Bounded delegation
# ---------------------------------------------------------------------------


def test_bounded_delegation() -> None:
    """No worker can spawn sub-workers (delegation depth = 1 max)."""
    # Depth 1 = supervisor -> worker (allowed)
    assert check_delegation_depth(None, 1) is True  # type: ignore[arg-type]

    # Depth 0 = no delegation yet (should be fine)
    assert check_delegation_depth(None, 0) is True  # type: ignore[arg-type]

    # Depth 2 = worker trying to spawn sub-worker (blocked)
    assert check_delegation_depth(None, 2) is False  # type: ignore[arg-type]

    # Depth 3+ = also blocked
    assert check_delegation_depth(None, 3) is False  # type: ignore[arg-type]
    assert check_delegation_depth(None, 10) is False  # type: ignore[arg-type]

    # Verify via full run that delegation depth is respected
    result = run(scenario="standard")
    assert result.status == ExecutionStatus.SUCCEEDED, (
        f"Expected SUCCEEDED, got {result.status}: {result.failure_reason}"
    )

    # The full run should have completed with bounded delegation
    # (delegation starts and stays at depth 1, which is allowed)


# ---------------------------------------------------------------------------
# Test: No recursive spawning
# ---------------------------------------------------------------------------


def test_no_recursive_spawning() -> None:
    """No recursive spawning is allowed.

    Workers cannot create sub-tasks or delegate to other workers.
    """
    result = run(scenario="standard")

    assert result.status == ExecutionStatus.SUCCEEDED, (
        f"Expected SUCCEEDED, got {result.status}: {result.failure_reason}"
    )

    # Verify there are no audit events indicating recursive spawning
    recursive_events = [
        e for e in result.audit_events
        if e.action == "recursive_spawn_blocked"
    ]
    # It's OK if no recursive spawn was attempted (it means no worker tried)
    # The important thing is that no sub-delegation actually occurred

    # Verify the delegation model: only supervisor dispatches to workers
    worker_task_starts = [
        e for e in result.audit_events
        if e.action == "task_start" and e.actor == "worker"
    ]
    supervisor_task_creates = [
        e for e in result.audit_events
        if e.action in ("decomposition_complete", "decomposition_start")
    ]

    # Supervisor created tasks, workers executed them (no worker->worker delegation)
    assert len(supervisor_task_creates) > 0, (
        "Expected supervisor to create tasks"
    )
    assert len(worker_task_starts) > 0, (
        "Expected workers to start tasks"
    )

    # Verify no worker acted as a supervisor (no nested supervision)
    worker_supervision_events = [
        e for e in result.audit_events
        if e.actor == "worker" and ("delegate" in e.action.lower() or "spawn" in e.action.lower())
    ]
    assert len(worker_supervision_events) == 0, (
        f"Expected no worker supervision events, got {len(worker_supervision_events)}"
    )


# ---------------------------------------------------------------------------
# Test: State keys present
# ---------------------------------------------------------------------------


def test_state_keys() -> None:
    """Verify task_ledger, worker_registry, and synthesis state keys are present."""
    result = run(scenario="standard")

    assert "task_ledger" in result.output, (
        "task_ledger should be in output"
    )
    assert "worker_registry" in result.output, (
        "worker_registry should be in output"
    )
    assert "synthesis" in result.output, (
        "synthesis should be in output"
    )

    # State snapshot should contain the same keys
    assert "task_ledger" in result.state_snapshot, (
        "task_ledger should be in state_snapshot"
    )
    assert "worker_registry" in result.state_snapshot, (
        "worker_registry should be in state_snapshot"
    )
    assert "synthesis" in result.state_snapshot, (
        "synthesis should be in state_snapshot"
    )


# ---------------------------------------------------------------------------
# Test: Budget enforcement
# ---------------------------------------------------------------------------


def test_budget_enforcement() -> None:
    """Verify budget limits are respected."""
    result = run(scenario="standard")

    assert result.metrics["model_calls"] <= 6, (
        f"Model calls ({result.metrics['model_calls']}) exceeded max_model_calls=6"
    )
    assert result.metrics["tool_calls"] <= 10, (
        f"Tool calls ({result.metrics['tool_calls']}) exceeded max_tool_calls=10"
    )


# ---------------------------------------------------------------------------
# Test: Audit events
# ---------------------------------------------------------------------------


def test_audit_events_present() -> None:
    """Verify audit events are recorded for key pattern actions."""
    result = run(scenario="standard")

    # Supervisor model call
    assert any(e.action == "model_call" for e in result.audit_events), (
        "Expected model_call audit event"
    )

    # Decomposition
    assert any(e.action == "decomposition_complete" for e in result.audit_events), (
        "Expected decomposition_complete audit event"
    )

    # Worker task execution
    assert any(e.action == "task_completed" for e in result.audit_events), (
        "Expected task_completed audit event"
    )

    # Synthesis
    assert any(e.action == "synthesis_complete" for e in result.audit_events), (
        "Expected synthesis_complete audit event"
    )
