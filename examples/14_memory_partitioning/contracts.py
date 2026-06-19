"""Pattern 14: Memory Partitioning — contracts and schemas.

Different memory types with separate stores, validation thresholds,
retention policies, and retrieval budgets.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MemoryEntry(BaseModel):
    """A single memory entry with type, content, confidence, and TTL."""

    id: str = Field(description="Unique memory entry identifier")
    type: str = Field(description="Memory type: working, session, episodic, user_profile")
    content: str = Field(description="Memory content text")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score (0.0-1.0)")
    timestamp: float = Field(description="Unix timestamp of creation")
    ttl: float | None = Field(default=None, description="TTL in seconds (None=no expiry)")


class UserProfile(BaseModel):
    """User profile with preferences and interaction history."""

    preferences: dict[str, str | float | bool] = Field(
        default_factory=dict,
        description="User preferences (e.g., timezone, theme, language)",
    )
    history: list[MemoryEntry] = Field(
        default_factory=list,
        description="Significant interaction history (high-confidence entries only)",
    )


# ── Confidence thresholds ──────────────────────────────────────────────────

# Minimum confidence for any memory write
MIN_CONFIDENCE_WRITE: float = 0.3

# Higher confidence required for profile updates
PROFILE_CONFIDENCE_THRESHOLD: float = 0.7

# Maximum entries returned in a single retrieval
RETRIEVAL_BUDGET: int = 10

# TTL defaults (seconds)
SESSION_MEMORY_TTL: float = 3600.0  # 1 hour
WORKING_MEMORY_TTL: float = 600.0  # 10 minutes
EPISODIC_MEMORY_TTL: float | None = None  # No expiry (permanent)
