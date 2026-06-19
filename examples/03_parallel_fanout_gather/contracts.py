"""Pattern 03: Parallel Fan-Out/Gather — contracts and schemas."""

from pydantic import BaseModel, Field


class SecurityEval(BaseModel):
    """Security evaluation of a vendor."""

    score: float = Field(ge=0.0, le=10.0, description="Security score (0-10)")
    issues: list[str] = Field(default_factory=list, description="Identified security issues")
    summary: str = Field(default="", description="Security evaluation summary")


class LegalEval(BaseModel):
    """Legal evaluation of a vendor."""

    score: float = Field(ge=0.0, le=10.0, description="Legal compliance score (0-10)")
    issues: list[str] = Field(default_factory=list, description="Identified legal issues")
    summary: str = Field(default="", description="Legal evaluation summary")


class OperationalEval(BaseModel):
    """Operational evaluation of a vendor."""

    score: float = Field(ge=0.0, le=10.0, description="Operational readiness score (0-10)")
    issues: list[str] = Field(default_factory=list, description="Identified operational issues")
    summary: str = Field(default="", description="Operational evaluation summary")


class FinancialEval(BaseModel):
    """Financial evaluation of a vendor."""

    score: float = Field(ge=0.0, le=10.0, description="Financial health score (0-10)")
    issues: list[str] = Field(default_factory=list, description="Identified financial issues")
    summary: str = Field(default="", description="Financial evaluation summary")


class VendorEvalSynthesis(BaseModel):
    """Aggregated synthesis of all vendor evaluations."""

    overall_score: float = Field(ge=0.0, le=10.0, description="Weighted overall score (0-10)")
    recommendation: str = Field(default="", description="Final recommendation (approve/reject/conditional)")
    summary: str = Field(default="", description="Synthesis summary across all dimensions")
