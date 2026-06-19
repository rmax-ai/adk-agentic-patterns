"""Contracts for Pattern 11: Agent Handoff.

Standalone reference copy — see agent.py for the authoritative definitions.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HandoffRequest(BaseModel):
    """Handoff request issued by a source agent to a target specialist."""

    reason: str = Field(description="Explicit explanation of why the handoff is needed")
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Minimised context passed from source to receiving agent",
    )
    from_agent: str = Field(description="Source agent identifier (e.g. 'support')")
    to_agent: str = Field(description="Target agent identifier (e.g. 'refund_specialist')")


class HandoffResponse(BaseModel):
    """Response from the receiving agent accepting or rejecting a handoff."""

    accepted: bool = Field(description="Whether the receiving agent accepts the handoff")
    reason: str = Field(description="Human-readable explanation for the decision")
