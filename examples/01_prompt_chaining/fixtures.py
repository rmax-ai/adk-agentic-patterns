"""Test fixtures for Pattern 01: Prompt Chaining.

Provides deterministic model responses for each stage of the pipeline.
One intentionally malformed upstream fixture — downstream must stop when validation fails.

NOTE: These fixtures are also inlined in agent.py to avoid relative import issues
(digit-prefixed directory names prevent package imports). This file serves as
a standalone reference copy.
"""

from adk_patterns.models import structured_response

# ── Stage 1: Incident Facts fixtures ──────────────────────────────────────

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

# ── Stage 2: Severity Assessment fixtures ─────────────────────────────────

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

# ── Stage 3: Stakeholder Summary fixtures ─────────────────────────────────

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
