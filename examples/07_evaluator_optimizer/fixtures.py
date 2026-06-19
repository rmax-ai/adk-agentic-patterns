"""Test fixtures for Pattern 07: Evaluator-Optimizer.

Maker fixtures generate Proposal objects; checker fixtures return RubricScores.
The two fixture sets are logically separate — no fixture key overlaps.
"""

# ── Maker fixtures ──────────────────────────────────────────────────────────
# These produce Proposal objects for different iteration stages.
MAKER_FIXTURES = {
    "maker_v1": {
        "title": "Migrate to PostgreSQL 16",
        "sections": [
            (
                "Summary: Upgrade the production database from PostgreSQL 14 to 16 "
                "for improved performance and new features."
            ),
            (
                "Impact: All services that depend on the shared Postgres instance "
                "will experience ~5 min of read-only mode during migration."
            ),
        ],
        "author": "infra-team",
    },
    "maker_v2": {
        "title": "Migrate to PostgreSQL 16 — v2",
        "sections": [
            (
                "Summary: Upgrade from PostgreSQL 14 to 16. Expected 20% query "
                "performance improvement and native SQL/JSON support."
            ),
            (
                "Impact: Services experience read-only mode during the 5 min cutover. "
                "Write queues buffer during the window."
            ),
            (
                "Migration Plan: 1) Standby replica with PG16. 2) Replay WAL. "
                "3) Validate. 4) Promote standby. 5) Redirect traffic."
            ),
        ],
        "author": "infra-team",
    },
    "maker_v3": {
        "title": "Migrate to PostgreSQL 16 — v3",
        "sections": [
            (
                "Summary: Database version upgrade delivering 20% faster queries, "
                "native JSON, and improved vacuum performance."
            ),
            (
                "Impact: 5 min read-only window. Write queues buffer automatically. "
                "Rollback is a DNS flip to the old primary."
            ),
            (
                "Migration Plan: Build PG16 replica → replay WAL → validate data → "
                "promote standby → switch DNS → decommission old primary."
            ),
            (
                "Rollback Plan: Flip DNS back to PG14 primary. Write queues drain "
                "naturally. Total RPO < 1 s."
            ),
        ],
        "author": "infra-team",
    },
    "maker_v4": {
        "title": "Migrate to PostgreSQL 16 — v4",
        "sections": [
            (
                "Summary: Zero-downtime upgrade from PG14 to PG16 with automated "
                "rollback and full observability."
            ),
            (
                "Impact: No user-facing downtime. Read replicas serve during cutover. "
                "Write buffers hold up to 60 s of traffic."
            ),
            (
                "Migration Plan: Deploy PG16 standby → sync via logical replication → "
                "validate checksums → promote → redirect via load balancer."
            ),
            (
                "Rollback Plan: Load balancer flips to old PG14 primary. "
                "Logical replication slot allows replay."
            ),
            (
                "Risk Assessment: Low — tested in staging three times. Monitoring "
                "dashboards validated for lag and replication status."
            ),
        ],
        "author": "infra-team",
    },
}

# ── Checker fixtures ────────────────────────────────────────────────────────
# These produce RubricScores for different iteration stages.
# Scores progress across versions to simulate improvement.
CHECKER_FIXTURES = {
    "checker_v1": {
        "clarity": 0.55,
        "completeness": 0.45,
        "feasibility": 0.60,
        "risk": 0.50,
        "overall": 0.53,
        "feedback": [
            "Summary: clear but too brief — add expected performance metrics.",
            "Impact: missing migration plan and rollback strategy.",
        ],
    },
    "checker_v2": {
        "clarity": 0.65,
        "completeness": 0.60,
        "feasibility": 0.70,
        "risk": 0.55,
        "overall": 0.63,
        "feedback": [
            "Summary: improved, metrics help. Add concrete benchmark targets.",
            "Impact: migration plan present but lacks validation steps.",
            "Migration Plan: clear steps, add data validation and monitoring.",
        ],
    },
    "checker_v3": {
        "clarity": 0.85,
        "completeness": 0.80,
        "feasibility": 0.84,
        "risk": 0.78,
        "overall": 0.82,
        "feedback": [
            "Summary: well structured with clear metrics. Consider including cost estimate.",
            "Impact: comprehensive. Rollback plan present.",
            "Migration Plan: thorough with validation. Add monitoring checkpoints.",
            "Rollback Plan: good. Add RPO/RTO targets explicitly.",
        ],
    },
    "checker_v4": {
        "clarity": 0.90,
        "completeness": 0.88,
        "feasibility": 0.85,
        "risk": 0.82,
        "overall": 0.86,
        "feedback": [
            "Summary: excellent. All key metrics and stakeholders identified.",
            "Impact: zero-downtime claim supported with evidence from staging.",
            "Migration Plan: fully detailed with validation at every step.",
            "Rollback Plan: comprehensive with RPO/RTO targets.",
            "Risk Assessment: thorough. Staging evidence strengthens confidence.",
        ],
    },
}

# ── Flat-score fixtures (for no-progress detection) ────────────────────────
# The same score repeated across iterations.
FLAT_MAKER_FIXTURES = {
    "flat_v1": {
        "title": "Flat Proposal v1",
        "sections": [
            "Summary: Upgrade internal tooling to latest SDK version.",
            "Impact: Low — mostly internal tooling.",
        ],
        "author": "tools-team",
    },
    "flat_v2": {
        "title": "Flat Proposal v2",
        "sections": [
            "Summary: Upgrade internal tooling to latest SDK version (updated).",
            "Impact: Low — mostly internal tooling.",
            "Migration Plan: Simple package version bump.",
        ],
        "author": "tools-team",
    },
    "flat_v3": {
        "title": "Flat Proposal v3",
        "sections": [
            "Summary: Upgrade internal tooling SDK (final draft).",
            "Impact: Low.",
            "Migration Plan: Bump version, update imports, run tests.",
            "Rollback Plan: Revert package.json change.",
        ],
        "author": "tools-team",
    },
}

FLAT_CHECKER_FIXTURES = {
    "flat_eval_v1": {
        "clarity": 0.60,
        "completeness": 0.55,
        "feasibility": 0.65,
        "risk": 0.50,
        "overall": 0.58,
        "feedback": [
            "Summary: adequate but vague on scope.",
            "Impact: missing timeline and owner.",
        ],
    },
    "flat_eval_v2": {
        "clarity": 0.60,
        "completeness": 0.55,
        "feasibility": 0.65,
        "risk": 0.50,
        "overall": 0.58,
        "feedback": [
            "Summary: still vague. Add specific SDK version target.",
            "Impact: still missing timeline.",
        ],
    },
    "flat_eval_v3": {
        "clarity": 0.60,
        "completeness": 0.55,
        "feasibility": 0.65,
        "risk": 0.50,
        "overall": 0.58,
        "feedback": [
            "Summary: no improvement in clarity.",
            "Impact: timeline and owner still missing.",
            "Migration Plan: lacks testing strategy.",
        ],
    },
}

# ── Independent evaluator fixtures ──────────────────────────────────────────
# Same draft evaluated by a different (independent) evaluator yields different scores.
INDEPENDENT_CHECKER = {
    "checker_independent": {
        "clarity": 0.72,
        "completeness": 0.68,
        "feasibility": 0.70,
        "risk": 0.65,
        "overall": 0.69,
        "feedback": [
            "Summary: clear but cost-benefit analysis missing.",
            "Impact: timeline and owner identified; add monitoring plan.",
        ],
    },
}
