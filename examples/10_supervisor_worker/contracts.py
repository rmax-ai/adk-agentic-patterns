"""Typed contracts for Pattern 10: Supervisor-Worker.

Defines Task, TaskLedger, WorkerRegistration, and related schemas
for product-launch review delegation.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Status of a task within the supervisor's ledger."""

    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class Task(BaseModel):
    """A single task assigned to a worker by the supervisor."""

    id: str = Field(description="Unique task identifier")
    name: str = Field(description="Human-readable task name")
    assignee: str = Field(description="Worker ID assigned to this task")
    status: TaskStatus = Field(
        default=TaskStatus.PENDING, description="Current task status"
    )
    result: dict[str, Any] = Field(
        default_factory=dict, description="Task output data"
    )


class TaskLedger(BaseModel):
    """The supervisor's typed task ledger.

    Contains all tasks, their assignments, statuses, and results.
    Only the supervisor can add entries; workers can only modify
    their own assigned task's result.
    """

    tasks: list[Task] = Field(default_factory=list, description="All tracked tasks")


class WorkerRegistration(BaseModel):
    """Registration record for a worker in the worker registry.

    Each worker has a unique ID and a list of capabilities (task types
    they are permitted to execute). Workers cannot modify tasks assigned
    to other workers.
    """

    id: str = Field(description="Unique worker identifier")
    capabilities: list[str] = Field(
        default_factory=list,
        description="List of task types this worker can handle",
    )


class SynthesisResult(BaseModel):
    """Final synthesis produced by the supervisor after all tasks complete."""

    summary: str = Field(description="Overall summary of the product-launch review")
    task_count: int = Field(description="Number of completed tasks")
    conclusions: dict[str, Any] = Field(
        default_factory=dict, description="Per-task conclusions"
    )
    status: str = Field(default="completed", description="Synthesis status")
