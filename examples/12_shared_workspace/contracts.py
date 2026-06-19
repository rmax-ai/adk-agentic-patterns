"""Contracts for Pattern 12: Shared Workspace / Blackboard.

Each claim carries author identity, evidence, confidence, and a version
for optimistic locking. The evidence_board is an append-only dict keyed
by claim.id.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Claim(BaseModel):
    """A single claim on the shared evidence board."""

    id: str = Field(description="Unique claim identifier")
    author: str = Field(description="Who contributed this claim")
    text: str = Field(description="The claim statement")
    evidence: str = Field(default="", description="Supporting evidence or citation")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Confidence score 0-1")
    status: str = Field(default="pending", description="pending, accepted, or rejected")
    version: int = Field(default=1, ge=1, description="Optimistic-lock version (incremented on update)")


# Type alias: evidence_board is a dict of claim_id -> Claim dict
EvidenceBoard = dict[str, dict[str, Any]]


class SynthesizerOutput(BaseModel):
    """Output of the synthesizer — a summary of accepted claims."""

    summary: str = Field(default="", description="Synthesis summary of accepted claims")
    accepted_count: int = Field(default=0, description="Number of accepted claims summarized")
    claim_ids: list[str] = Field(default_factory=list, description="IDs of accepted claims")
