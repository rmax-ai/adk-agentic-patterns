"""Pydantic contracts for the Sequential Specialists pattern.

Each stage produces a typed output that serves as the input contract
for the next stage. This enforces strong data consistency between
specialist agents — no ad-hoc dict passing between stages.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractedClaim(BaseModel):
    """Extracted claim details from raw submission text (Stage 1)."""

    claim_id: str = Field(description="Unique identifier for the claim")
    policy_number: str = Field(description="Insurance policy number")
    claimant_name: str = Field(description="Full name of the claimant")
    incident_date: str = Field(description="Date when the incident occurred")
    incident_type: str = Field(
        description="Type of incident: 'auto_accident', 'property_damage', 'medical', 'theft', 'other'"
    )
    description: str = Field(description="Brief factual description of the incident")
    amount_claimed: float = Field(ge=0.0, description="Monetary amount claimed in the policy currency")


class EligibilityVerdict(BaseModel):
    """Eligibility decision derived from claim details (Stage 2)."""

    is_eligible: bool = Field(description="Whether the claim is eligible for coverage")
    eligible_amount: float = Field(ge=0.0, description="Maximum eligible payout amount after policy rules")
    reason: str = Field(description="Human-readable reason for the eligibility decision")
    deductible: float = Field(ge=0.0, description="Applicable deductible amount")


class FraudScreeningResult(BaseModel):
    """Fraud screening outcome based on claim and eligibility data (Stage 3)."""

    is_suspicious: bool = Field(description="Whether the claim exhibits fraud indicators")
    risk_score: float = Field(ge=0.0, le=1.0, description="Fraud risk score from 0.0 (low) to 1.0 (high)")
    flags: list[str] = Field(default_factory=list, description="Specific fraud indicators detected")
    recommendation: str = Field(
        description="Recommended action: 'approve', 'review', 'escalate', 'deny'"
    )


class ClaimExplanation(BaseModel):
    """Final human-readable explanation for the claim decision (Stage 4)."""

    summary: str = Field(description="One-paragraph summary of the claim and decision")
    coverage_details: str = Field(description="Details of coverage applicable to the claim")
    payment_amount: float = Field(ge=0.0, description="Final payment amount after eligibility and adjustments")
    next_steps: list[str] = Field(description="Actionable next steps for the claimant")
