"""Memory tool helpers for Pattern 14: Memory Partitioning.

Pure dict-based memory stores with confidence validation,
stale entry eviction, and retrieval budget enforcement.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

from adk_patterns.shared import RunContext

# Add example dir to path for sibling imports
_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))

from contracts import (  # noqa: E402
    EPISODIC_MEMORY_TTL,
    MIN_CONFIDENCE_WRITE,
    PROFILE_CONFIDENCE_THRESHOLD,
    RETRIEVAL_BUDGET,
    SESSION_MEMORY_TTL,
    WORKING_MEMORY_TTL,
    MemoryEntry,
    UserProfile,
)


def is_stale(entry: MemoryEntry, now: float | None = None) -> bool:
    """Check if a memory entry has expired based on its TTL."""
    if entry.ttl is None:
        return False
    now = now or time.time()
    return (now - entry.timestamp) > entry.ttl


def validate_write(entry: MemoryEntry, is_profile: bool = False) -> str | None:
    """Validate a memory write. Returns error string or None if valid.

    Profile updates require higher confidence than other writes.
    """
    if entry.confidence < MIN_CONFIDENCE_WRITE:
        return f"Confidence {entry.confidence:.2f} below minimum threshold {MIN_CONFIDENCE_WRITE}"
    if is_profile and entry.confidence < PROFILE_CONFIDENCE_THRESHOLD:
        return (
            f"Profile update requires confidence >= {PROFILE_CONFIDENCE_THRESHOLD}, "
            f"got {entry.confidence:.2f}"
        )
    return None


def write_working_memory(
    ctx: RunContext,
    store: dict[str, Any],
    key: str,
    entry: MemoryEntry,
) -> str | None:
    """Write to working memory with validation."""
    error = validate_write(entry, is_profile=False)
    if error:
        ctx.audit("memory", "write_rejected", resource="working", outcome="failure", metadata={"reason": error})
        return error
    store[key] = entry
    ctx.audit("memory", "write", resource="working", outcome="success", metadata={"key": key, "type": entry.type})
    return None


def read_working_memory(
    ctx: RunContext,
    store: dict[str, Any],
    key: str,
) -> MemoryEntry | None:
    """Read from working memory with stale check."""
    ctx.audit("memory", "read", resource="working", outcome="in_progress", metadata={"key": key})
    entry = store.get(key)
    if entry is None:
        return None
    if is_stale(entry):
        del store[key]
        ctx.audit("memory", "stale_evicted", resource="working", outcome="success", metadata={"key": key})
        return None
    ctx.audit("memory", "read", resource="working", outcome="success", metadata={"key": key})
    return entry


def write_session_memory(
    ctx: RunContext,
    store: dict[str, Any],
    key: str,
    entry: MemoryEntry,
) -> str | None:
    """Write to session memory with validation."""
    error = validate_write(entry, is_profile=False)
    if error:
        ctx.audit("memory", "write_rejected", resource="session", outcome="failure", metadata={"reason": error})
        return error
    store[key] = entry
    ctx.audit("memory", "write", resource="session", outcome="success", metadata={"key": key, "type": entry.type})
    return None


def read_session_memory(
    ctx: RunContext,
    store: dict[str, Any],
    key: str,
) -> MemoryEntry | None:
    """Read from session memory with stale check."""
    ctx.audit("memory", "read", resource="session", outcome="in_progress", metadata={"key": key})
    entry = store.get(key)
    if entry is None:
        return None
    if is_stale(entry):
        del store[key]
        ctx.audit("memory", "stale_evicted", resource="session", outcome="success", metadata={"key": key})
        return None
    ctx.audit("memory", "read", resource="session", outcome="success", metadata={"key": key})
    return entry


def write_episodic_memory(
    ctx: RunContext,
    store: list[MemoryEntry],
    entry: MemoryEntry,
) -> str | None:
    """Write to episodic memory with validation. No raw conversation dumping."""
    error = validate_write(entry, is_profile=False)
    if error:
        ctx.audit("memory", "write_rejected", resource="episodic", outcome="failure", metadata={"reason": error})
        return error
    store.append(entry)
    ctx.audit("memory", "write", resource="episodic", outcome="success", metadata={"id": entry.id, "type": entry.type})
    return None


def read_episodic_memory(
    ctx: RunContext,
    store: list[MemoryEntry],
    max_entries: int = RETRIEVAL_BUDGET,
) -> list[MemoryEntry]:
    """Read from episodic memory with stale check and retrieval budget."""
    ctx.audit("memory", "read", resource="episodic", outcome="in_progress")
    now = time.time()
    valid: list[MemoryEntry] = []
    stale_ids: list[str] = []
    for entry in store:
        if is_stale(entry, now):
            stale_ids.append(entry.id)
        else:
            valid.append(entry)
    # Remove stale entries
    if stale_ids:
        store[:] = [e for e in store if e.id not in stale_ids]
        ctx.audit("memory", "stale_evicted", resource="episodic", outcome="success", metadata={"count": len(stale_ids)})
    # Apply retrieval budget
    result = valid[:max_entries]
    ctx.audit("memory", "read", resource="episodic", outcome="success", metadata={"returned": len(result), "budget": max_entries})
    return result


def update_user_profile(
    ctx: RunContext,
    profile: UserProfile,
    entry: MemoryEntry,
) -> str | None:
    """Update user profile with high-confidence validation only."""
    error = validate_write(entry, is_profile=True)
    if error:
        ctx.audit("memory", "profile_update_rejected", outcome="failure", metadata={"reason": error})
        return error
    # Only high-confidence entries go into profile history
    profile.history.append(entry)
    ctx.audit("memory", "profile_updated", outcome="success", metadata={"id": entry.id})
    return None


def set_preference(
    ctx: RunContext,
    profile: UserProfile,
    key: str,
    value: str | float | bool,
) -> None:
    """Set a user preference (no confidence threshold needed)."""
    profile.preferences[key] = value
    ctx.audit("memory", "preference_set", outcome="success", metadata={"key": key, "value": value})


def check_raw_conversation_dumping(
    content: str,
    episodic_store: list[MemoryEntry],
) -> bool:
    """Check if raw conversation text has been dumped into episodic memory.

    Returns True if raw chat history (consecutive user/assistant turns) is found.
    """
    # Detect indicators of raw conversation dumping
    raw_indicators = [
        "user:",
        "assistant:",
        "[user]",
        "[assistant]",
        "User said:",  # common pattern from models that dump
        "Assistant said:",
        "Previous turns:",
        "Conversation history:",
    ]
    content_lower = content.lower()
    indicator_count = sum(1 for ind in raw_indicators if ind.lower() in content_lower)
    # If we detect multiple turn indicators, it's likely raw conversation
    if indicator_count >= 2:
        return True
    # Also check episodic store for raw conversation patterns
    for entry in episodic_store:
        if entry.type == "raw_conversation":
            return True
    return False
