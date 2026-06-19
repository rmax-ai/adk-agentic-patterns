"""Pattern 02: Router-Specialist — typed contracts and schemas.

Standalone reference copy — see agent.py for the authoritative definitions.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RouterVerdict(BaseModel):
    """Routing decision produced by the model with confidence score.

    When confidence falls below the threshold (0.6), a deterministic
    fallback re-routes to the 'general' specialist.
    """

    route: str = Field(
        description="Target specialist route: billing, account, technical, or general",
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence in the routing decision (0.0–1.0)",
    )
    reasoning: str = Field(
        default="", description="Brief explanation of the routing decision",
    )


class SpecialistOutput(BaseModel):
    """Output produced by a specialist agent after handling a routed request."""

    specialist: str = Field(description="Which specialist handled the request")
    response: str = Field(description="Response from the specialist")
    tools_used: list[str] = Field(
        default_factory=list,
        description="Tool names invoked by this specialist",
    )
