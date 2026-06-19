"""Pattern 07: Evaluator-Optimizer — contracts and schemas.

Scenario: Generate a technical change proposal and iteratively improve it
against a rubric. The maker (proposal generator) and checker (evaluator) use
separate fixture sets and return typed contracts.
"""

from pydantic import BaseModel, Field


class Proposal(BaseModel):
    """A technical change proposal with structured sections."""

    title: str = Field(description="Short descriptive title of the proposal")
    sections: list[str] = Field(
        default_factory=list,
        description="Proposal sections (e.g., summary, impact, migration plan, rollback)",
    )
    author: str = Field(default="", description="Author of the proposal")


class RubricScores(BaseModel):
    """Rubric-based evaluation scores with localized per-section feedback.

    Each dimension is scored 0.0–1.0.  The `overall` field is a combined score
    (e.g. the mean or weighted average).  `feedback` contains one entry per
    evaluated section, allowing the maker to improve section by section.
    """

    clarity: float = Field(ge=0.0, le=1.0, description="Score for clarity of writing and structure")
    completeness: float = Field(ge=0.0, le=1.0, description="Score for completeness of coverage")
    feasibility: float = Field(ge=0.0, le=1.0, description="Score for feasibility and practicality")
    risk: float = Field(ge=0.0, le=1.0, description="Score for risk assessment quality")
    overall: float = Field(ge=0.0, le=1.0, description="Combined overall score")
    feedback: list[str] = Field(
        default_factory=list,
        description="Per-section localized feedback string for each evaluated section",
    )
