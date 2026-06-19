"""ScriptedModel fixtures for Pattern 10: Supervisor-Worker.

Each scenario defines a sequence of ModelResponse objects replayed via
ScriptedModel.set_response_sequence() for deterministic testing.

The supervisor makes ONE model call per run. The fixture at index [0]
provides the decomposition plan (task_ledger + worker_registry).
"""

from __future__ import annotations

from adk_patterns.models import structured_response


# ---------------------------------------------------------------------------
# Helper: standard task ledger builders
# ---------------------------------------------------------------------------


def _standard_tasks() -> list[dict]:
    """Return a standard product-launch review task list with assignments."""
    return [
        {
            "id": "task-market",
            "name": "Market Analysis",
            "assignee": "worker_market",
            "status": "pending",
            "result": {},
        },
        {
            "id": "task-tech",
            "name": "Technical Review",
            "assignee": "worker_tech",
            "status": "pending",
            "result": {},
        },
        {
            "id": "task-compliance",
            "name": "Compliance Check",
            "assignee": "worker_compliance",
            "status": "pending",
            "result": {},
        },
        {
            "id": "task-launch",
            "name": "Launch Readiness",
            "assignee": "worker_launch",
            "status": "pending",
            "result": {},
        },
    ]


def _standard_workers() -> list[dict]:
    """Return a standard worker registry."""
    return [
        {
            "id": "worker_market",
            "capabilities": ["market_analysis", "competitor_intel", "pricing_review"],
        },
        {
            "id": "worker_tech",
            "capabilities": ["technical_review", "security_audit", "performance_benchmark"],
        },
        {
            "id": "worker_compliance",
            "capabilities": ["compliance_check", "regulatory_review", "data_privacy"],
        },
        {
            "id": "worker_launch",
            "capabilities": ["launch_readiness", "go_to_market"],
        },
    ]


def _three_tasks() -> list[dict]:
    """Return a 3-task plan for the bounded-delegation test."""
    return [
        {
            "id": "task-market",
            "name": "Market Analysis",
            "assignee": "worker_market",
            "status": "pending",
            "result": {},
        },
        {
            "id": "task-tech",
            "name": "Technical Review",
            "assignee": "worker_tech",
            "status": "pending",
            "result": {},
        },
        {
            "id": "task-compliance",
            "name": "Compliance Check",
            "assignee": "worker_compliance",
            "status": "pending",
            "result": {},
        },
    ]


def _three_workers() -> list[dict]:
    """Return a 3-worker registry."""
    return [
        {
            "id": "worker_market",
            "capabilities": ["market_analysis", "competitor_intel", "pricing_review"],
        },
        {
            "id": "worker_tech",
            "capabilities": ["technical_review", "security_audit", "performance_benchmark"],
        },
        {
            "id": "worker_compliance",
            "capabilities": ["compliance_check", "regulatory_review", "data_privacy"],
        },
    ]


# ---------------------------------------------------------------------------
# Fixture response sequences (index [0] is consumed by supervisor model call)
# ---------------------------------------------------------------------------

STANDARD_DECOMPOSITION = [
    structured_response({
        "task_ledger": {"tasks": _standard_tasks()},
        "worker_registry": _standard_workers(),
    }),
]

THREE_TASK_DECOMPOSITION = [
    structured_response({
        "task_ledger": {"tasks": _three_tasks()},
        "worker_registry": _three_workers(),
    }),
]

BOUNDED_DELEGATION = [
    structured_response({
        "task_ledger": {"tasks": _three_tasks()},
        "worker_registry": _three_workers(),
    }),
]

# -- Fixture registry --------------------------------------------------------

FIXTURES: dict[str, list] = {
    "standard": STANDARD_DECOMPOSITION,
    "three_tasks": THREE_TASK_DECOMPOSITION,
    "bounded_delegation": BOUNDED_DELEGATION,
}
