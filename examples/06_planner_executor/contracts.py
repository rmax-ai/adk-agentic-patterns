"""Typed contracts for Pattern 06: Planner-Executor.

Defines ExecutionPlan, Task, and related schemas for conference setup planning.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Status of a task within an execution plan."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class Task(BaseModel):
    """A single task within an ExecutionPlan."""

    id: str = Field(description="Unique task identifier")
    name: str = Field(description="Human-readable task name")
    deps: list[str] = Field(
        default_factory=list,
        description="Task IDs this task depends on (must complete first)",
    )
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Current task status")
    result: dict[str, Any] = Field(default_factory=dict, description="Task output data")
    tool_name: str = Field(description="Name of the tool to invoke for this task")
    tool_args: dict[str, Any] = Field(
        default_factory=dict, description="Arguments to pass to the tool"
    )


class ExecutionPlan(BaseModel):
    """A complete plan composed of typed tasks with dependency ordering."""

    tasks: list[Task] = Field(description="Ordered list of tasks to execute")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Plan-level metadata (conference name, date, etc.)"
    )


class ExecutionPlanResult(BaseModel):
    """Result of executing an ExecutionPlan."""

    plan: ExecutionPlan = Field(description="The plan that was executed")
    task_results: dict[str, dict[str, Any]] = Field(
        default_factory=dict, description="Task ID -> result dict"
    )
    overall_status: str = Field(default="pending", description="Overall execution status")
    failure_reason: str | None = Field(default=None, description="If execution failed, why")
