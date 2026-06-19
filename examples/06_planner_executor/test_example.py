"""Tests for Pattern 06: Planner-Executor.

Covers:
- test_plan_and_execute — Planner creates plan, Executor runs tasks in order
- test_replan_after_failure — Venue failure triggers replan, new plan executed
- test_plan_validation — Invalid plan rejected before execution
- test_planner_no_write_tools — Planner cannot call executor tools
- test_max_replan_budget — Second replan attempt fails
- test_task_dependency_order — Tasks respect dependencies
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

from agent import run  # noqa: E402

from adk_patterns.contracts import ExecutionStatus  # noqa: E402


# ---------------------------------------------------------------------------
# Happy path: full plan-and-execute cycle
# ---------------------------------------------------------------------------


def test_plan_and_execute() -> None:
    """Planner creates a valid plan, Executor runs tasks in dependency order."""
    result = run(scenario="plan_and_execute")

    assert result.status == ExecutionStatus.SUCCEEDED, (
        f"Expected SUCCEEDED, got {result.status}: {result.failure_reason}"
    )
    assert result.output is not None
    assert "execution_plan" in result.output
    assert "task_results" in result.output

    state = result.output
    plan = state.get("execution_plan", {})
    tasks = plan.get("tasks", []) if isinstance(plan, dict) else plan.tasks if hasattr(plan, "tasks") else []
    assert len(tasks) > 0, "Plan should contain tasks"

    task_results = state.get("task_results", {})
    assert len(task_results) > 0, "Executor should have produced task results"

    # All tasks should have completed
    for task in tasks:
        tid = task.get("id") if isinstance(task, dict) else task.id
        assert tid in task_results, f"Task {tid} was not executed"

    # Budget should be respected
    assert result.metrics["model_calls"] <= 5
    assert result.metrics["tool_calls"] <= 10
    assert result.metrics["iterations"] <= 3


# ---------------------------------------------------------------------------
# Replan after venue failure
# ---------------------------------------------------------------------------


def test_replan_after_failure() -> None:
    """Venue failure triggers replan, new plan executed successfully."""
    result = run(scenario="replan_after_failure")

    assert result.status == ExecutionStatus.SUCCEEDED, (
        f"Expected SUCCEEDED, got {result.status}: {result.failure_reason}"
    )
    assert result.output is not None

    state = result.output
    # The replan should have occurred
    assert state.get("replan_count", 0) >= 1, "Expected at least 1 replan"

    task_results = state.get("task_results", {})
    assert len(task_results) > 0, "Executor should have produced task results"

    # Replan audit events should be present
    replan_events = [e for e in result.audit_events if e.action == "replan"]
    assert len(replan_events) >= 1, "Expected at least 1 replan audit event"


# ---------------------------------------------------------------------------
# Plan validation
# ---------------------------------------------------------------------------


def test_plan_validation() -> None:
    """Invalid plan (duplicate IDs, cyclic deps) rejected before execution."""
    result = run(scenario="plan_validation")

    # Should fail with plan validation error
    assert result.status in (
        ExecutionStatus.FAILED,
        ExecutionStatus.REJECTED,
    ), f"Expected FAILED/REJECTED, got {result.status}"

    # Should have a failure reason about plan validation
    assert result.failure_reason is not None
    assert "validation" in result.failure_reason.lower() or "plan" in result.failure_reason.lower(), (
        f"Failure reason should mention plan validation: {result.failure_reason}"
    )

    # No tasks should have been executed
    if result.output and "task_results" in result.output:
        assert len(result.output["task_results"]) == 0, (
            "No tasks should be executed for an invalid plan"
        )

    # There should be a plan_validation_failed audit event
    validation_failures = [
        e for e in result.audit_events if e.action == "plan_validation_failed"
    ]
    assert len(validation_failures) >= 1, (
        "Expected plan_validation_failed audit event"
    )


# ---------------------------------------------------------------------------
# Planner has no write tools
# ---------------------------------------------------------------------------


def test_planner_no_write_tools() -> None:
    """Planner cannot call executor tools — only read/plan capabilities."""
    result = run(scenario="planner_no_write_tools")

    assert result.status == ExecutionStatus.SUCCEEDED, (
        f"Expected SUCCEEDED, got {result.status}: {result.failure_reason}"
    )

    # Verify the planner never directly called executor tools
    # Planner audit events should only have model_call and parse events
    planner_events = [e for e in result.audit_events if e.actor == "planner"]
    for event in planner_events:
        assert event.action != "tool_call", (
            f"Planner made a tool call: {event}"
        )
        assert event.resource not in (
            "check_availability", "book_venue", "order_catering", "schedule_event"
        ), f"Planner accessed executor tool: {event.resource}"

    # Executor should have run the tasks
    executor_events = [e for e in result.audit_events if e.actor == "executor"]
    assert len(executor_events) > 0, "Expected executor audit events"

    # At least some tool calls should be present
    tool_calls = [e for e in result.audit_events if e.resource in (
        "check_availability", "book_venue", "order_catering", "schedule_event"
    )]
    # These could be task_start or tool_call events referencing tools
    has_tool_activity = any(
        e.resource in ("check_availability", "book_venue", "order_catering", "schedule_event")
        for e in result.audit_events
    )
    assert result.metrics["tool_calls"] > 0, "Expected at least 1 tool call"


# ---------------------------------------------------------------------------
# Max replan budget
# ---------------------------------------------------------------------------


def test_max_replan_budget() -> None:
    """Second replan attempt fails due to replan budget limit."""
    result = run(scenario="max_replan_budget")

    # Should fail because the replan budget is exceeded
    assert result.status == ExecutionStatus.FAILED, (
        f"Expected FAILED, got {result.status}: {result.failure_reason}"
    )

    # Failure reason should mention replan budget
    assert result.failure_reason is not None
    assert "replan" in result.failure_reason.lower() or "budget" in result.failure_reason.lower(), (
        f"Failure reason should mention replan budget: {result.failure_reason}"
    )

    # Should have replan_budget_exceeded audit event
    budget_events = [
        e for e in result.audit_events if e.action == "replan_budget_exceeded"
    ]
    assert len(budget_events) >= 1, "Expected replan_budget_exceeded audit event"

    # State should have replan_count = 1 (max)
    if result.output and "replan_count" in result.output:
        assert result.output["replan_count"] >= 1


# ---------------------------------------------------------------------------
# Task dependency ordering
# ---------------------------------------------------------------------------


def test_task_dependency_order() -> None:
    """Tasks respect dependency ordering — task with deps doesn't start before dep completes."""
    result = run(scenario="task_dependency_order")

    assert result.status == ExecutionStatus.SUCCEEDED, (
        f"Expected SUCCEEDED, got {result.status}: {result.failure_reason}"
    )
    assert result.output is not None

    state = result.output
    task_results = state.get("task_results", {})

    # task-1 (check availability) should run first
    assert "task-1" in task_results, "task-1 should have been executed"

    # task-2 (book venue) depends on task-1, so task-1 must have run before task-2
    # task-3 (catering) depends on task-1, so task-1 must have run before task-3
    # Verify the dependency order through audit events
    task_start_events = [
        e for e in result.audit_events
        if e.action == "task_start"
    ]

    # Sort by event index (they should be naturally ordered in the list)
    task_order = [e.resource for e in task_start_events if e.resource]
    # task-1 should come before task-2 and task-3
    if "task-1" in task_order and "task-2" in task_order:
        assert task_order.index("task-1") < task_order.index("task-2"), (
            f"task-1 should start before task-2, got order: {task_order}"
        )
    if "task-1" in task_order and "task-3" in task_order:
        assert task_order.index("task-1") < task_order.index("task-3"), (
            f"task-1 should start before task-3, got order: {task_order}"
        )

    # All tasks should have results
    assert len(task_results) >= 3, (
        f"Expected at least 3 task results, got {len(task_results)}"
    )
