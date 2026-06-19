"""Fixture data for Sequential Specialists pattern tests.

Each stage has its own set of named fixtures. Shared state keys
prevent data leakage across stages — the extraction fixture's fields
are consumed only by stage 2, which produces its own keys consumed
by stage 3, etc.
"""

from __future__ import annotations

from typing import Any

from adk_patterns.models import ScriptedModel, structured_response

# ── Stage 1: Extraction ─────────────────────────────────────────────────────

STAGE1_FIXTURES = {
    # Valid claim — clean, straightforward auto accident
    "stage1_valid_auto": structured_response({
        "claim_id": "CLM-2026-001",
        "policy_number": "POL-AUTO-88723",
        "claimant_name": "Jane Doe",
        "incident_date": "2026-06-01",
        "incident_type": "auto_accident",
        "description": "Rear-end collision at intersection of Main St and 5th Ave. "
        "Minor damage to rear bumper. No injuries reported. Police report filed.",
        "amount_claimed": 3500.00,
    }),
    # Valid claim — eligible for screening
    "stage1_valid_property": structured_response({
        "claim_id": "CLM-2026-002",
        "policy_number": "POL-HOME-45129",
        "claimant_name": "John Smith",
        "incident_date": "2026-05-28",
        "incident_type": "property_damage",
        "description": "Water damage from burst pipe in basement kitchen. "
        "Flooring and drywall affected. Plumber repaired the leak.",
        "amount_claimed": 8200.00,
    }),
    # Ineligible claim — policy lapsed
    "stage1_ineligible": structured_response({
        "claim_id": "CLM-2026-003",
        "policy_number": "POL-AUTO-99999",
        "claimant_name": "Bob Wilson",
        "incident_date": "2026-06-15",
        "incident_type": "auto_accident",
        "description": "Single-vehicle collision with guardrail on Highway 101. "
        "Front-end damage. Driver reported no injuries.",
        "amount_claimed": 12000.00,
    }),
    # Fraud-suspicious claim — multiple red flags
    "stage1_fraud_suspicious": structured_response({
        "claim_id": "CLM-2026-004",
        "policy_number": "POL-AUTO-33412",
        "claimant_name": "Alice Reed",
        "incident_date": "2026-06-10",
        "incident_type": "theft",
        "description": "Vehicle stolen from mall parking lot during business hours. "
        "Keys were reported lost two weeks prior. Claimant filed police report "
        "three days after the alleged incident date.",
        "amount_claimed": 45000.00,
    }),
}

# ── Stage 2: Eligibility ────────────────────────────────────────────────────

STAGE2_FIXTURES = {
    "stage2_approved_auto": structured_response({
        "is_eligible": True,
        "eligible_amount": 3500.00,
        "reason": "Policy is active and in good standing. "
        "Collision coverage applies with a $500 deductible. "
        "Claim amount is within policy limits.",
        "deductible": 500.00,
    }),
    "stage2_approved_property": structured_response({
        "is_eligible": True,
        "eligible_amount": 8200.00,
        "reason": "Homeowners policy covers water damage from burst pipe. "
        "Claim is within dwelling coverage limits. "
        "$1,000 deductible applies.",
        "deductible": 1000.00,
    }),
    "stage2_denied_lapsed": structured_response({
        "is_eligible": False,
        "eligible_amount": 0.00,
        "reason": "Policy POL-AUTO-99999 was lapsed at the time of the incident. "
        "Premium payments were 45 days overdue. "
        "No coverage is available for this claim.",
        "deductible": 0.00,
    }),
    "stage2_approved_fraud": structured_response({
        "is_eligible": True,
        "eligible_amount": 45000.00,
        "reason": "Comprehensive coverage applies. "
        "Policy is active with theft protection included. "
        "$1,500 deductible applies.",
        "deductible": 1500.00,
    }),
}

# ── Stage 3: Fraud Screening ───────────────────────────────────────────────

STAGE3_FIXTURES = {
    "stage3_clean_auto": structured_response({
        "is_suspicious": False,
        "risk_score": 0.05,
        "flags": [],
        "recommendation": "approve",
    }),
    "stage3_clean_property": structured_response({
        "is_suspicious": False,
        "risk_score": 0.12,
        "flags": [],
        "recommendation": "approve",
    }),
    "stage3_fraud_theft": structured_response({
        "is_suspicious": True,
        "risk_score": 0.87,
        "flags": [
            "delayed police report (3 days after incident)",
            "keys reported lost shortly before theft",
            "claimed amount significantly above market value",
        ],
        "recommendation": "escalate",
    }),
}

# ── Stage 4: Explanation ────────────────────────────────────────────────────

STAGE4_FIXTURES = {
    "stage4_approved_auto": structured_response({
        "summary": (
            "Claim CLM-2026-001 (auto accident on June 1, 2026) has been reviewed and approved. "
            "The policy is active and collision coverage applies. After a $500 deductible, "
            "the net payment amount is $3,000.00."
        ),
        "coverage_details": (
            "Collision coverage under policy POL-AUTO-88723. "
            "Coverage limit: $25,000. Deductible: $500. "
            "No exclusions apply to this incident type."
        ),
        "payment_amount": 3000.00,
        "next_steps": [
            "Schedule repair at an approved auto body shop",
            "Submit repair estimate for pre-approval",
            "Payment will be issued within 5 business days of estimate approval",
        ],
    }),
    "stage4_approved_property": structured_response({
        "summary": (
            "Claim CLM-2026-002 (water damage on May 28, 2026) has been reviewed and approved. "
            "The homeowners policy covers burst pipe damage. After a $1,000 deductible, "
            "the net payment amount is $7,200.00."
        ),
        "coverage_details": (
            "Dwelling coverage under policy POL-HOME-45129. "
            "Coverage limit: $300,000. Deductible: $1,000. "
            "Water damage from burst pipe is a covered peril."
        ),
        "payment_amount": 7200.00,
        "next_steps": [
            "Submit itemized repair invoices for reimbursement",
            "Request inspector visit to assess structural damage",
            "Payment issued directly to claimant or contractor",
        ],
    }),
}


# ── Combined fixture map for convenience ────────────────────────────────────

ALL_FIXTURES: dict[str, dict[str, Any]] = {
    "stage1": STAGE1_FIXTURES,
    "stage2": STAGE2_FIXTURES,
    "stage3": STAGE3_FIXTURES,
    "stage4": STAGE4_FIXTURES,
}


def register_all(model: ScriptedModel) -> None:
    """Register all fixtures on the given ScriptedModel instance."""
    for stage_fixtures in ALL_FIXTURES.values():
        model.register_fixtures(stage_fixtures)
