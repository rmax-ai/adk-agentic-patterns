"""Pattern 00: Single Model Call — contracts and schemas."""

from pydantic import BaseModel, Field


class ClassificationResult(BaseModel):
    """Support request classification with confidence score."""

    category: str = Field(description="One of: billing, account, technical, general")
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(default="", description="Brief classification rationale")
