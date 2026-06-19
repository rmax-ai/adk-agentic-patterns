"""ScriptedModel fixtures for Pattern 06: Planner-Executor.

Each scenario defines a sequence of ModelResponse objects replayed via
ScriptedModel.set_response_sequence() for deterministic testing.

IMPORTANT: Only index [0] of each sequence is consumed by the planner's
model.invoke(). Subsequent entries are unused because the executor calls
tools directly, not through model.invoke(). To simulate tool failures,
the PLANNER must emit tasks that use an unavailable venue (venue-003).

Fixtures cover:
- plan_and_execute — Planner creates a valid plan, Executor runs it
- replan_after_failure — Venue failure triggers replan, new plan executed
- plan_validation — Invalid plan rejected before execution
- planner_no_write_tools — Planner cannot call executor tools
- max_replan_budget — Second replan attempt fails
- task_dependency_order — Tasks respect dependencies
"""
from __future__ import annotations

from adk_patterns.models import structured_response


# ---------------------------------------------------------------------------
# Helper: standard task builders
# ---------------------------------------------------------------------------


def _plan_tasks() -> list[dict]:
    """Return a standard conference setup plan with dependencies (venue-001)."""
    return [
        {
            "id": "task-1",
            "name": "Check venue availability",
            "deps": [],
            "status": "pending",
            "result": {},
            "tool_name": "check_availability",
            "tool_args": {"venue_id": "venue-001"},
        },
        {
            "id": "task-2",
            "name": "Book the venue",
            "deps": ["task-1"],
            "status": "pending",
            "result": {},
            "tool_name": "book_venue",
            "tool_args": {"venue_id": "venue-001"},
        },
        {
            "id": "task-3",
            "name": "Order catering",
            "deps": ["task-2"],
            "status": "pending",
            "result": {},
            "tool_name": "order_catering",
            "tool_args": {"venue_id": "venue-001", "attendees": 100},
        },
        {
            "id": "task-4",
            "name": "Schedule conference event",
            "deps": ["task-2"],
            "status": "pending",
            "result": {},
            "tool_name": "schedule_event",
            "tool_args": {
                "title": "Annual Tech Conference",
                "date": "2026-07-15",
                "venue_id": "venue-001",
            },
        },
    ]


def _failing_tasks() -> list[dict]:
    """Return a plan that uses venue-003 (unavailable — triggers booking failure)."""
    return [
        {
            "id": "task-1",
            "name": "Check venue availability",
            "deps": [],
            "status": "pending",
            "result": {},
            "tool_name": "check_availability",
            "tool_args": {"venue_id": "venue-003"},
        },
        {
            "id": "task-2",
            "name": "Book the venue",
            "deps": ["task-1"],
            "status": "pending",
            "result": {},
            "tool_name": "book_venue",
            "tool_args": {"venue_id": "venue-003"},
        },
    ]


def _replan_tasks() -> list[dict]:
    """Return a fallback plan using venue-002 (available)."""
    return [
        {
            "id": "task-1",
            "name": "Check venue availability (alternative)",
            "deps": [],
            "status": "pending",
            "result": {},
            "tool_name": "check_availability",
            "tool_args": {"venue_id": "venue-002"},
        },
        {
            "id": "task-2",
            "name": "Book the alternative venue",
            "deps": ["task-1"],
            "status": "pending",
            "result": {},
            "tool_name": "book_venue",
            "tool_args": {"venue_id": "venue-002"},
        },
        {
            "id": "task-3",
            "name": "Order catering (alternative venue)",
            "deps": ["task-2"],
            "status": "pending",
            "result": {},
            "tool_name": "order_catering",
            "tool_args": {"venue_id": "venue-002", "attendees": 100},
        },
        {
            "id": "task-4",
            "name": "Schedule conference event",
            "deps": ["task-2"],
            "status": "pending",
            "result": {},
            "tool_name": "schedule_event",
            "tool_args": {
                "title": "Annual Tech Conference",
                "date": "2026-07-15",
                "venue_id": "venue-002",
            },
        },
    ]


# ---------------------------------------------------------------------------
# Fixture responses (only index [0] is consumed per planner call)
# ---------------------------------------------------------------------------

PLAN_AND_EXECUTE = [
    structured_response(
        {
            "tasks": _plan_tasks(),
            "metadata": {
                "conference_name": "Annual Tech Conference",
                "date": "2026-07-15",
                "attendees": 100,
            },
        }
    ),
]

REPLAN_AFTER_FAILURE = [
    # [0] Initial plan uses venue-003 (unavailable) -> triggers failure + replan
    structured_response(
        {
            "tasks": _failing_tasks(),
            "metadata": {
                "conference_name": "Annual Tech Conference",
                "date": "2026-07-15",
                "attendees": 100,
            },
        }
    ),
    # [1] Replan plan (consumed on second planner call) uses venue-002
    structured_response(
        {
            "tasks": _replan_tasks(),
            "metadata": {
                "conference_name": "Annual Tech Conference",
                "date": "2026-07-15",
                "attendees": 100,
                "replan": True,
            },
        }
    ),
]

PLAN_VALIDATION = [
    structured_response(
        {
            "tasks": [
                {
                    "id": "task-1",
                    "name": "Check venue",
                    "deps": [],
                    "status": "pending",
                    "result": {},
                    "tool_name": "check_availability",
                    "tool_args": {"venue_id": "venue-001"},
                },
                {
                    "id": "task-1",  # duplicate ID
                    "name": "Book venue",
                    "deps": ["task-1"],
                    "status": "pending",
                    "result": {},
                    "tool_name": "book_venue",
                    "tool_args": {"venue_id": "venue-001"},
                },
                {
                    "id": "task-3",
                    "name": "Catering",
                    "deps": ["task-4"],  # depends on task not yet listed
                    "status": "pending",
                    "result": {},
                    "tool_name": "order_catering",
                    "tool_args": {"venue_id": "venue-001", "attendees": 100},
                },
                {
                    "id": "task-4",
                    "name": "Schedule",
                    "deps": ["task-3"],  # cycle: task-3 -> task-4 -> task-3
                    "status": "pending",
                    "result": {},
                    "tool_name": "schedule_event",
                    "tool_args": {
                        "title": "Conference",
                        "date": "2026-07-15",
                        "venue_id": "venue-001",
                    },
                },
            ],
            "metadata": {},
        }
    ),
]

PLANNER_NO_WRITE_TOOLS = [
    structured_response(
        {
            "tasks": _plan_tasks(),
            "metadata": {
                "conference_name": "Annual Tech Conference",
                "date": "2026-07-15",
                "attendees": 100,
            },
        }
    ),
]

MAX_REPLAN_BUDGET = [
    # [0] Initial plan uses venue-003 (unavailable) -> triggers failure
    structured_response(
        {
            "tasks": _failing_tasks(),
            "metadata": {"conference_name": "Tech Conf", "date": "2026-07-15", "attendees": 100},
        }
    ),
    # [1] Replan also uses venue-003 -> fails again -> replan budget exceeded
    structured_response(
        {
            "tasks": _failing_tasks(),
            "metadata": {"replan": True},
        }
    ),
]

TASK_DEPENDENCY_ORDER = [
    structured_response(
        {
            "tasks": [
                {
                    "id": "task-1",
                    "name": "Check venue",
                    "deps": [],
                    "status": "pending",
                    "result": {},
                    "tool_name": "check_availability",
                    "tool_args": {"venue_id": "venue-001"},
                },
                {
                    "id": "task-2",
                    "name": "Book venue",
                    "deps": ["task-1"],
                    "status": "pending",
                    "result": {},
                    "tool_name": "book_venue",
                    "tool_args": {"venue_id": "venue-001"},
                },
                {
                    "id": "task-3",
                    "name": "Order catering",
                    "deps": ["task-1"],
                    "status": "pending",
                    "result": {},
                    "tool_name": "order_catering",
                    "tool_args": {"venue_id": "venue-001", "attendees": 100},
                },
            ],
            "metadata": {},
        }
    ),
]

# -- Fixture registry --------------------------------------------------------

FIXTURES: dict[str, list] = {
    "plan_and_execute": PLAN_AND_EXECUTE,
    "replan_after_failure": REPLAN_AFTER_FAILURE,
    "plan_validation": PLAN_VALIDATION,
    "planner_no_write_tools": PLANNER_NO_WRITE_TOOLS,
    "max_replan_budget": MAX_REPLAN_BUDGET,
    "task_dependency_order": TASK_DEPENDENCY_ORDER,
}
