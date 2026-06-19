"""Pattern 20: Dynamic Workflow.

Scenario: Process a data-quality incident where execution branches depend
on discovered conditions. The incident type is classified via a single model
call, then pure Python control flow routes execution to the appropriate branch.

Demonstrates:
- Programmatic conditional flow (Python if/else, not model-driven routing)
- Dynamic branching based on discovered issue types
- Nested deterministic functions for sub-checks
- Bounded recursion / iteration (no infinite branching)
- Explicit state transitions (recorded in state_snapshot)
- Branch-coverage tests (all paths exercised)
- Avoid model-driven routing where ordinary code can decide
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from adk_patterns.config import Config
from adk_patterns.contracts import PatternRunResult
from adk_patterns.models import ScriptedModel, structured_response
from adk_patterns.shared import RunContext, run_scope


# ── Fixture data ───────────────────────────────────────────────────────────

CLASSIFICATION_FIXTURES = {
    "schema_violation": structured_response({
        "incident_type": "schema_violation",
        "confidence": 0.95,
        "description": (
            "User profile table has rows violating NOT NULL constraint "
            "on email field"
        ),
    }),
    "missing_data": structured_response({
        "incident_type": "missing_data",
        "confidence": 0.92,
        "description": (
            "Orders table missing line items for 47 recent transactions"
        ),
    }),
    "stale_data": structured_response({
        "incident_type": "stale_data",
        "confidence": 0.88,
        "description": (
            "Product inventory timestamps not updated in over 6 hours"
        ),
    }),
    "unknown": structured_response({
        "incident_type": "unknown",
        "confidence": 0.45,
        "description": (
            "Unusual pattern detected but cannot classify with available data"
        ),
    }),
}

INCIDENT_REPORTS: dict[str, str] = {
    "schema_violation": (
        "Data quality alert: User profile table has 12 rows with NULL email "
        "addresses violating the NOT NULL constraint. These rows were inserted "
        "by a batch ETL job that ran at 2026-06-19T03:00:00Z."
    ),
    "missing_data": (
        "Data quality alert: Orders table shows 47 transactions without "
        "corresponding line items. The order ingestion pipeline may have "
        "skipped details for orders placed between 2026-06-18T12:00:00Z and "
        "2026-06-19T12:00:00Z."
    ),
    "stale_data": (
        "Data quality alert: Product inventory table shows last_updated "
        "timestamps that are over 6 hours old for 234 SKUs in warehouse "
        "WH-03. Expected freshness is under 5 minutes."
    ),
    "unknown": (
        "Data quality alert: Anomaly detected in clickstream data. Pattern "
        "does not match any known issue signature. Further investigation "
        "needed."
    ),
}

_VALID_SCENARIOS = frozenset({"schema_violation", "missing_data", "stale_data", "unknown"})


# ── Branch functions (pure Python — no model calls) ────────────────────────


def validate_schema(ctx: RunContext, incident: dict[str, Any]) -> dict[str, Any]:
    """Branch: Schema violation — check constraints and resolve.

    Deterministic Python function. No model calls.
    """
    ctx.audit("validate_schema", "branch_enter", resource="constraint_check")
    ctx.record_iteration()

    constraints_checked = ["NOT_NULL", "UNIQUE", "FOREIGN_KEY", "DATA_TYPE"]
    violations_found = 12
    severity = "high" if violations_found > 5 else "low"

    resolution: dict[str, Any] = {
        "branch": "validate_schema",
        "action": "constraint_validation",
        "constraints_checked": constraints_checked,
        "violations_found": violations_found,
        "severity": severity,
        "remediation": (
            "Patch the ETL job to handle NULL values, then run a backfill "
            "query to set default values for existing NULL rows."
        ),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }

    transitions: list[dict[str, Any]] = [
        {
            "from": "classification",
            "to": "validate_schema",
            "reason": (
                f"incident_type=schema_violation "
                f"(confidence={incident.get('confidence', 0)})"
            ),
        },
        {
            "from": "validate_schema",
            "to": "resolution",
            "reason": f"constraint_check_complete ({violations_found} violations)",
        },
    ]

    ctx.snapshot_state({
        "incident_type": "schema_violation",
        "branch_path": ["classification", "validate_schema", "resolution"],
        "transitions": transitions,
        "resolution": resolution,
    })
    ctx.audit("validate_schema", "branch_exit", outcome="success",
              metadata={"violations": violations_found})
    return resolution


def assess_completeness(ctx: RunContext, incident: dict[str, Any]) -> dict[str, Any]:
    """Branch: Missing data — gap analysis and resolve.

    Deterministic Python function. No model calls.
    """
    ctx.audit("assess_completeness", "branch_enter", resource="gap_analysis")
    ctx.record_iteration()

    total_records = 47
    completeness_pct = 0.0

    resolution: dict[str, Any] = {
        "branch": "assess_completeness",
        "action": "gap_analysis",
        "total_records": total_records,
        "missing_segments": ["line_items", "shipping_details"],
        "completeness_pct": completeness_pct,
        "severity": "critical",
        "remediation": (
            "Re-run the order ingestion pipeline with enhanced validation. "
            "Add data completeness checks to the ETL process."
        ),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }

    transitions: list[dict[str, Any]] = [
        {
            "from": "classification",
            "to": "assess_completeness",
            "reason": (
                f"incident_type=missing_data "
                f"(confidence={incident.get('confidence', 0)})"
            ),
        },
        {
            "from": "assess_completeness",
            "to": "resolution",
            "reason": "gap_analysis_complete",
        },
    ]

    ctx.snapshot_state({
        "incident_type": "missing_data",
        "branch_path": ["classification", "assess_completeness", "resolution"],
        "transitions": transitions,
        "resolution": resolution,
    })
    ctx.audit("assess_completeness", "branch_exit", outcome="success")
    return resolution


def check_freshness(ctx: RunContext, incident: dict[str, Any]) -> dict[str, Any]:
    """Branch: Stale data — timestamp validation and resolve.

    Deterministic Python function. No model calls.
    """
    ctx.audit("check_freshness", "branch_enter", resource="timestamp_validation")
    ctx.record_iteration()

    stale_hours = 6.5
    threshold_hours = 0.083  # 5 minutes
    skus_affected = 234

    resolution: dict[str, Any] = {
        "branch": "check_freshness",
        "action": "timestamp_validation",
        "stale_hours": stale_hours,
        "threshold_hours": threshold_hours,
        "skus_affected": skus_affected,
        "severity": "medium",
        "remediation": (
            "Restart the inventory sync pipeline for warehouse WH-03. "
            "Increase monitoring frequency for last_updated timestamps."
        ),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }

    transitions: list[dict[str, Any]] = [
        {
            "from": "classification",
            "to": "check_freshness",
            "reason": (
                f"incident_type=stale_data "
                f"(confidence={incident.get('confidence', 0)})"
            ),
        },
        {
            "from": "check_freshness",
            "to": "resolution",
            "reason": "timestamp_validation_complete",
        },
    ]

    ctx.snapshot_state({
        "incident_type": "stale_data",
        "branch_path": ["classification", "check_freshness", "resolution"],
        "transitions": transitions,
        "resolution": resolution,
    })
    ctx.audit("check_freshness", "branch_exit", outcome="success")
    return resolution


def escalate_to_analyst(ctx: RunContext, incident: dict[str, Any]) -> dict[str, Any]:
    """Branch: Unknown — escalate to human analyst for manual review.

    Deterministic Python function. No model calls.
    """
    ctx.audit("escalate_to_analyst", "branch_enter", resource="human_escalation")
    ctx.record_iteration()

    resolution: dict[str, Any] = {
        "branch": "escalate_to_analyst",
        "action": "human_escalation",
        "escalation_level": "senior_data_analyst",
        "required_investigation": [
            "Review clickstream anomaly patterns",
            "Cross-reference with known incident signatures",
            "Check for upstream data source changes",
        ],
        "severity": "low",
        "remediation": (
            "Ticket created for senior analyst review. "
            "Escalation includes full incident context and raw data samples."
        ),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }

    transitions: list[dict[str, Any]] = [
        {
            "from": "classification",
            "to": "escalate_to_analyst",
            "reason": (
                f"incident_type=unknown "
                f"(confidence={incident.get('confidence', 0)})"
            ),
        },
        {
            "from": "escalate_to_analyst",
            "to": "resolution",
            "reason": "escalation_ticket_created",
        },
    ]

    ctx.snapshot_state({
        "incident_type": "unknown",
        "branch_path": ["classification", "escalate_to_analyst", "resolution"],
        "transitions": transitions,
        "resolution": resolution,
    })
    ctx.audit("escalate_to_analyst", "branch_exit", outcome="success")
    return resolution


# ── Branch router ──────────────────────────────────────────────────────────

BRANCH_ROUTES: dict[str, Any] = {
    "schema_violation": validate_schema,
    "missing_data": assess_completeness,
    "stale_data": check_freshness,
    "unknown": escalate_to_analyst,
}


def classify_and_route(
    ctx: RunContext,
    model: ScriptedModel,
    report_text: str,
    scenario: str,
) -> dict[str, Any]:
    """Classify the incident and route to the appropriate branch.

    Only ONE model call is made here. All routing is pure Python if/elif.
    """
    ctx.audit("classification", "model_call", resource="incident_report")
    ctx.record_model_call(tokens=100)
    ctx.record_iteration()

    fixture_key = scenario if scenario in _VALID_SCENARIOS else "schema_violation"
    response = model.invoke(
        system_instruction=(
            "Classify the following data-quality incident into one of these "
            "types: schema_violation, missing_data, stale_data, unknown. "
            "Return the classification with confidence score and description."
        ),
        messages=[
            {"role": "user", "content": f"__FIXTURE__:{fixture_key} {report_text}"}
        ],
    )

    ctx.audit("classification", "model_response", outcome="success")

    data = response.structured_output
    if data is None or "incident_type" not in data:
        ctx.audit("classification", "classification_failed", outcome="failure",
                  metadata={"reason": "no_classification"})
        incident_type = "unknown"
        data = {"incident_type": "unknown", "confidence": 0.0,
                "description": "Classification failed"}
    else:
        incident_type = data["incident_type"]

    ctx.audit("classification", "classified", outcome="success",
              metadata={
                  "incident_type": incident_type,
                  "confidence": data.get("confidence", 0),
              })

    # Snapshot classification
    ctx.snapshot_state({
        "incident_type": incident_type,
        "classification": data,
        "branch_path": ["classification"],
        "transitions": [],
    })

    # Route to branch (pure Python dict dispatch — same as if/elif)
    branch_fn = BRANCH_ROUTES.get(incident_type, escalate_to_analyst)

    ctx.audit("router", "branch_selected", outcome="success",
              metadata={"incident_type": incident_type,
                        "branch": branch_fn.__name__})

    resolution = branch_fn(ctx, data)

    # Collect transitions from the last state snapshot (set by the branch)
    branch_path = ctx.state_snapshots[-1].get("branch_path", []) if ctx.state_snapshots else []
    transitions = ctx.state_snapshots[-1].get("transitions", []) if ctx.state_snapshots else []

    return {
        "incident_type": incident_type,
        "classification": data,
        "branch_path": branch_path,
        "transitions": transitions,
        "resolution": resolution,
    }


# ── Run entry point ────────────────────────────────────────────────────────


def run(config: Config | None = None, scenario: str = "default") -> PatternRunResult:
    """Execute the dynamic workflow: classify → route → branch → resolve.

    Args:
        config: Application configuration (uses defaults if None).
        scenario: Test scenario (schema_violation, missing_data,
                  stale_data, unknown).

    Returns:
        PatternRunResult with final output and audit trail.
    """
    model = ScriptedModel()
    model.register_fixtures(CLASSIFICATION_FIXTURES)

    scenario_key = scenario if scenario in _VALID_SCENARIOS else "schema_violation"
    report_text = INCIDENT_REPORTS.get(scenario_key,
                                       INCIDENT_REPORTS["schema_violation"])

    with run_scope(
        "dynamic-workflow",
        scenario,
        max_model_calls=3,
        max_tool_calls=0,
        max_iterations=3,
    ) as ctx:
        result = classify_and_route(ctx, model, report_text, scenario_key)
        ctx.output = result
        ctx.snapshot_state(result)

    return ctx.to_result()


# ── CLI entry point ─────────────────────────────────────────────────────────


def main(config: Config | None = None, scenario: str = "default") -> PatternRunResult:
    """Standard entry point called by CLI."""
    return run(config=config, scenario=scenario)
