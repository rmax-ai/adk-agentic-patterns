"""Pattern 01: Prompt Chaining.

Scenario: Transform a raw product incident report through three chained stages:
  Stage 1 — Normalized facts extraction
  Stage 2 — Severity assessment
  Stage 3 — Stakeholder summary

Each stage has its own output state key and Pydantic contract for validation.
If any stage's output fails schema validation, the chain stops immediately.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError

from adk_patterns.contracts import PatternRunResult
from adk_patterns.config import Config
from adk_patterns.models import ScriptedModel, structured_response
from adk_patterns.shared import RunContext, run_scope


# ── Inline contracts (avoid relative imports for digit-prefixed dir) ──────


class IncidentFacts(BaseModel):
    """Normalized facts extracted from a raw product incident report (Stage 1)."""

    product: str = Field(description="Product or service affected (e.g., 'API Gateway')")
    issue_type: str = Field(description="Type of issue (e.g., 'outage', 'data_loss', 'latency')")
    customer_tier: str = Field(description="Customer tier affected: 'enterprise', 'business', 'developer', 'all'")
    description: str = Field(description="Concise factual description of the incident")
    timestamp: str | None = Field(default=None, description="When the incident occurred or was reported")


class SeverityAssessment(BaseModel):
    """Severity assessment derived from incident facts (Stage 2)."""

    severity: str = Field(description="Severity level: 'critical', 'high', 'medium', 'low'")
    impact_score: float = Field(ge=0.0, le=1.0, description="Impact score from 0.0 (none) to 1.0 (total)")
    affected_users_estimate: int = Field(ge=0, description="Estimated number of affected users")
    business_impact: str = Field(description="Description of business impact (revenue, reputation, compliance)")


class StakeholderSummary(BaseModel):
    """Executive stakeholder summary derived from severity assessment (Stage 3)."""

    summary: str = Field(description="One-paragraph executive summary for stakeholders")
    recommended_actions: list[str] = Field(description="Prioritized list of recommended actions")
    notified_stakeholders: list[str] = Field(description="List of stakeholder groups notified")
    requires_escalation: bool = Field(description="Whether this incident requires executive escalation")


# ── Fixture data (stage-prefixed keys to avoid collisions across stages) ──

STAGE1_FIXTURES = {
    "stage1_security_breach": structured_response({
        "product": "API Gateway",
        "issue_type": "security_breach",
        "customer_tier": "enterprise",
        "description": (
            "An unauthorized third party accessed the API Gateway admin panel "
            "for approximately 47 minutes between 03:14 UTC and 04:01 UTC. "
            "Customer API keys for 3 enterprise tenants may have been exposed."
        ),
        "timestamp": "2026-06-19T03:14:00Z",
    }),
    "stage1_latency_outage": structured_response({
        "product": "Database Service",
        "issue_type": "latency_outage",
        "customer_tier": "all",
        "description": (
            "Elevated p99 latency on Database Service cluster db-prod-7 "
            "from 200ms to 12s between 02:00 UTC and 02:35 UTC. "
            "Redis read replicas failed over automatically. No data loss."
        ),
        "timestamp": "2026-06-19T02:00:00Z",
    }),
    "stage1_degraded_performance": structured_response({
        "product": "Content Delivery Network",
        "issue_type": "degraded_performance",
        "customer_tier": "business",
        "description": (
            "CDN edge nodes in us-east-1 served stale cached content for "
            "approximately 12 minutes. Invalidation queue was backed up due to "
            "a surge in purge requests from automated deployments."
        ),
        "timestamp": "2026-06-19T05:22:00Z",
    }),
    # Intentionally malformed upstream fixture — missing required 'product' field
    "stage1_malformed_facts": structured_response({
        "issue_type": "unknown_event",
        "customer_tier": "all",
        "description": "Some undetermined event occurred but no product is specified.",
    }),
}

STAGE2_FIXTURES = {
    "stage2_security_breach": structured_response({
        "severity": "critical",
        "impact_score": 0.92,
        "affected_users_estimate": 15000,
        "business_impact": (
            "Enterprise customer data potentially exposed. "
            "Compliance obligations under SOC2 and GDPR may be triggered. "
            "Long-term reputational damage if API keys were exfiltrated."
        ),
    }),
    "stage2_latency_outage": structured_response({
        "severity": "high",
        "impact_score": 0.75,
        "affected_users_estimate": 45000,
        "business_impact": (
            "All customer tiers experienced slowdowns. "
            "SLA credits may be owed to business and enterprise accounts. "
            "No data loss, but user-facing latency degraded experience."
        ),
    }),
    "stage2_degraded_performance": structured_response({
        "severity": "medium",
        "impact_score": 0.40,
        "affected_users_estimate": 8000,
        "business_impact": (
            "Business-tier customers served stale content. "
            "Minor reputational impact. No regulatory concerns."
        ),
    }),
}

STAGE3_FIXTURES = {
    "stage3_security_breach": structured_response({
        "summary": (
            "A critical security breach in the API Gateway admin panel exposed "
            "enterprise customer API keys for 47 minutes. SOC2 and GDPR compliance "
            "reporting is required. All affected tenants have been notified and keys rotated."
        ),
        "recommended_actions": [
            "Rotate all exposed API keys immediately",
            "Enable MFA on admin panel access",
            "Conduct full security audit of access logs",
            "Notify affected enterprise customers with incident report",
        ],
        "notified_stakeholders": [
            "Security Team",
            "Enterprise Customer Success",
            "VP of Engineering",
            "Compliance Officer",
        ],
        "requires_escalation": True,
    }),
    "stage3_latency_outage": structured_response({
        "summary": (
            "A 35-minute latency outage on the Database Service cluster db-prod-7 "
            "affected all customer tiers. Redis failover operated correctly. "
            "No data was lost. SLA monitoring is in progress to determine credit eligibility."
        ),
        "recommended_actions": [
            "Investigate root cause of p99 latency spike",
            "Review Redis replica failover timing",
            "Update incident runbook with findings",
        ],
        "notified_stakeholders": [
            "Infrastructure Team",
            "Customer Support Lead",
            "SRE Team",
        ],
        "requires_escalation": False,
    }),
    "stage3_degraded_performance": structured_response({
        "summary": (
            "CDN edge nodes in us-east-1 served stale content for 12 minutes "
            "due to a backed-up invalidation queue. Business-tier customers were "
            "primarily affected. No data loss or security implications."
        ),
        "recommended_actions": [
            "Add rate limiting to cache purge API",
            "Implement queue depth monitoring alerts",
            "Review CDN invalidation strategy",
        ],
        "notified_stakeholders": [
            "Platform Engineering Team",
            "Customer Support Lead",
        ],
        "requires_escalation": False,
    }),
}


# ── Incident report texts ─────────────────────────────────────────────────

INCIDENT_REPORTS = {
    "security_breach": (
        "URGENT: At 03:14 UTC today, our monitoring system detected unauthorized "
        "access to the API Gateway admin panel. The access persisted for 47 minutes "
        "until credentials were revoked at 04:01 UTC. This affects our enterprise "
        "tier customers. Internal investigation suggests API keys for 3 tenants "
        "may have been exposed. Security team has been paged."
    ),
    "latency_outage": (
        "Incident reported at 02:00 UTC: Database Service cluster db-prod-7 is "
        "experiencing severe latency. p99 latency jumped from baseline 200ms to "
        "over 12 seconds. All customer tiers are affected. Redis read replicas "
        "failed over automatically at 02:05 UTC. No data loss reported. Issue "
        "resolved at 02:35 UTC after scaling up read replicas."
    ),
    "degraded_performance": (
        "At 05:22 UTC, CDN edge nodes in us-east-1 started serving stale cached "
        "content. This was caused by a backed-up invalidation queue following a "
        "surge of purge requests from automated deployments. Approximately 12 "
        "minutes of stale content served. Primary impact was on business-tier "
        "customers. Issue resolved automatically when the queue drained."
    ),
    "malformed_facts": (
        "Something happened in the system. We're not sure what. No product info "
        "available. Multiple customers may be affected but we can't confirm."
    ),
}


# ── Scene-to-fixture helpers ──────────────────────────────────────────────

_VALID_SCENARIOS = frozenset({"security_breach", "latency_outage", "degraded_performance", "malformed_facts"})


# ── Stage functions ───────────────────────────────────────────────────────


def stage1_extract_facts(
    ctx: RunContext,
    model: ScriptedModel,
    scenario: str,
    request_text: str,
) -> IncidentFacts | None:
    """Stage 1: Extract normalized facts from a raw incident report.

    Returns a validated IncidentFacts or None if validation fails.
    """
    ctx.audit("stage1", "model_call", resource="incident_report")
    ctx.record_model_call(tokens=100)

    fixture_key = f"stage1_{scenario}" if scenario in _VALID_SCENARIOS else "stage1_security_breach"
    response = model.invoke(
        system_instruction="Extract normalized incident facts from the report.",
        messages=[{"role": "user", "content": f"__FIXTURE__:{fixture_key} {request_text}"}],
    )

    ctx.audit("stage1", "model_response", outcome="success")

    data = response.structured_output
    if data is None:
        ctx.audit("stage1", "validation_failed", outcome="failure", metadata={"reason": "no_structured_output"})
        ctx.mark_failed("Stage 1: model returned no structured output")
        return None

    try:
        facts = IncidentFacts(**data)
    except ValidationError as e:
        ctx.audit("stage1", "validation_failed", outcome="failure", metadata={"errors": str(e)})
        ctx.mark_failed(f"Stage 1: schema validation failed — {e.errors()}")
        return None

    ctx.snapshot_state({"stage1_facts": facts.model_dump()})
    return facts


def stage2_assess_severity(
    ctx: RunContext,
    model: ScriptedModel,
    facts: IncidentFacts,
    scenario: str,
) -> SeverityAssessment | None:
    """Stage 2: Assess severity from normalized incident facts.

    Only runs if Stage 1 succeeded. Returns validated SeverityAssessment or None.
    """
    ctx.audit("stage2", "model_call", resource="incident_severity")
    ctx.record_model_call(tokens=100)

    fixture_key = f"stage2_{scenario}" if scenario in _VALID_SCENARIOS else "stage2_security_breach"
    response = model.invoke(
        system_instruction=(
            "Assess the severity of the incident based on the facts provided. "
            "Return a typed severity assessment with severity level, impact score, "
            "affected user estimate, and business impact description."
        ),
        messages=[
            {"role": "user", "content": f"__FIXTURE__:{fixture_key} Facts: {facts.model_dump_json()}"},
        ],
    )

    ctx.audit("stage2", "model_response", outcome="success")

    data = response.structured_output
    if data is None:
        ctx.audit("stage2", "validation_failed", outcome="failure", metadata={"reason": "no_structured_output"})
        ctx.mark_failed("Stage 2: model returned no structured output")
        return None

    try:
        severity = SeverityAssessment(**data)
    except ValidationError as e:
        ctx.audit("stage2", "validation_failed", outcome="failure", metadata={"errors": str(e)})
        ctx.mark_failed(f"Stage 2: schema validation failed — {e.errors()}")
        return None

    ctx.snapshot_state({"stage2_severity": severity.model_dump()})
    return severity


def stage3_generate_summary(
    ctx: RunContext,
    model: ScriptedModel,
    facts: IncidentFacts,
    severity: SeverityAssessment,
    scenario: str,
) -> StakeholderSummary | None:
    """Stage 3: Generate stakeholder summary from facts and severity.

    Only runs if Stages 1 and 2 both succeeded.
    """
    ctx.audit("stage3", "model_call", resource="stakeholder_summary")
    ctx.record_model_call(tokens=100)

    fixture_key = f"stage3_{scenario}" if scenario in _VALID_SCENARIOS else "stage3_security_breach"
    response = model.invoke(
        system_instruction=(
            "Generate an executive stakeholder summary based on the incident "
            "facts and severity assessment. Include recommended actions "
            "and notified stakeholder groups."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"__FIXTURE__:{fixture_key} "
                    f"Facts: {facts.model_dump_json()} "
                    f"Severity: {severity.model_dump_json()}"
                ),
            },
        ],
    )

    ctx.audit("stage3", "model_response", outcome="success")

    data = response.structured_output
    if data is None:
        ctx.audit("stage3", "validation_failed", outcome="failure", metadata={"reason": "no_structured_output"})
        ctx.mark_failed("Stage 3: model returned no structured output")
        return None

    try:
        summary = StakeholderSummary(**data)
    except ValidationError as e:
        ctx.audit("stage3", "validation_failed", outcome="failure", metadata={"errors": str(e)})
        ctx.mark_failed(f"Stage 3: schema validation failed — {e.errors()}")
        return None

    ctx.snapshot_state({"stage3_summary": summary.model_dump()})
    return summary


# ── Run entry point ───────────────────────────────────────────────────────


def run(config: Config | None = None, scenario: str = "default") -> PatternRunResult:
    """Execute the full prompt chain: facts → severity → summary.

    Args:
        config: Application configuration (uses defaults if None).
        scenario: Test scenario name (security_breach, latency_outage,
                  degraded_performance, malformed_facts).

    Returns:
        PatternRunResult with the final output or failure information.
    """
    model = ScriptedModel()
    model.register_fixtures(STAGE1_FIXTURES)
    model.register_fixtures(STAGE2_FIXTURES)
    model.register_fixtures(STAGE3_FIXTURES)

    scenario_key = scenario if scenario in _VALID_SCENARIOS else "security_breach"
    request_text = INCIDENT_REPORTS.get(scenario_key, INCIDENT_REPORTS["security_breach"])

    with run_scope(
        "prompt-chaining",
        scenario,
        max_model_calls=3,
        max_tool_calls=0,
        max_iterations=0,
    ) as ctx:
        # ── Stage 1: Extract facts ────────────────────────────────────────
        facts = stage1_extract_facts(ctx, model, scenario_key, request_text)
        if facts is None:
            ctx.output = {"stage1_facts": "validation_failed"}
            return ctx.to_result()

        # ── Stage 2: Assess severity ──────────────────────────────────────
        severity = stage2_assess_severity(ctx, model, facts, scenario_key)
        if severity is None:
            ctx.output = {
                "stage1_facts": facts.model_dump(),
                "stage2_severity": "validation_failed",
            }
            return ctx.to_result()

        # ── Stage 3: Generate summary ─────────────────────────────────────
        summary = stage3_generate_summary(ctx, model, facts, severity, scenario_key)
        if summary is None:
            ctx.output = {
                "stage1_facts": facts.model_dump(),
                "stage2_severity": severity.model_dump(),
                "stage3_summary": "validation_failed",
            }
            return ctx.to_result()

        # ── Success: aggregate all outputs ──────────────────────────────
        ctx.output = {
            "stage1_facts": facts.model_dump(),
            "stage2_severity": severity.model_dump(),
            "stage3_summary": summary.model_dump(),
        }
        ctx.snapshot_state(ctx.output)

    return ctx.to_result()


# ── CLI entry point ───────────────────────────────────────────────────────


def main(config: Config | None = None, scenario: str = "default") -> PatternRunResult:
    """Standard entry point called by CLI."""
    return run(config=config, scenario=scenario)
