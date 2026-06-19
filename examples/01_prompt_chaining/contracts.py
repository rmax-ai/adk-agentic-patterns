"""Pattern 01: Prompt Chaining — contracts and schemas.

Three sequential stages: facts extraction → severity assessment → stakeholder summary.
Each stage has its own Pydantic contract for cross-stage validation.
"""

from pydantic import BaseModel, Field


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
