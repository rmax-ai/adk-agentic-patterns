"""Pattern 14: Memory Partitioning — Personal Task Assistant.

Separate stores and interfaces for working, session, episodic, and user-profile
memory. Memory writes require confidence validation with different thresholds.
Retrieval budgets, stale-memory eviction, memory poisoning protection, and
no raw conversation dumping into long-term memory.
"""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from adk_patterns.contracts import ExecutionStatus, PatternRunResult
from adk_patterns.models import ScriptedModel, structured_response
from adk_patterns.shared import RunContext, run_scope

# Add example dir to path for sibling imports
_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))

from contracts import (  # noqa: E402
    MemoryEntry,
    UserProfile,
    SESSION_MEMORY_TTL,
    WORKING_MEMORY_TTL,
    EPISODIC_MEMORY_TTL,
    RETRIEVAL_BUDGET,
    MIN_CONFIDENCE_WRITE,
    PROFILE_CONFIDENCE_THRESHOLD,
)
from tools import (  # noqa: E402
    check_raw_conversation_dumping,
    read_episodic_memory,
    read_session_memory,
    read_working_memory,
    set_preference,
    update_user_profile,
    write_episodic_memory,
    write_session_memory,
    write_working_memory,
)


# ── Fixture keys (inlined) ─────────────────────────────────────────────────


# ── Default budgets ────────────────────────────────────────────────────────

MAX_MODEL_CALLS = 3
MAX_TOOL_CALLS = 5


# ── Agent: Memory Partitioning Agent ───────────────────────────────────────


def get_default_state() -> dict[str, Any]:
    """Return the default memory state structure."""
    return {
        "working_memory": {},
        "session_memory": {},
        "episodic_memory": [],
        "user_profile": UserProfile(),
    }


def run_memory_agent(
    ctx: RunContext,
    model: ScriptedModel,
    operation: str = "default",
) -> PatternRunResult:
    """Run the memory partitioning agent for the given operation.

    Operations:
    - "default" / "working": test working memory read/write
    - "session": test session memory read/write
    - "episodic": test episodic memory read/write
    - "profile": test user profile load/update
    - "stale": test stale memory eviction
    - "poisoning": test low-confidence write rejection
    - "no_dump": test raw conversation dump prevention
    - "budget": test retrieval budget
    """
    state = get_default_state()

    ctx.audit("memory_agent", "start", outcome="success", metadata={"operation": operation})

    # ── Budget check ───────────────────────────────────────────────────────
    budget_status = ctx.check_budget()
    if budget_status is not None:
        ctx.status = budget_status
        return ctx.to_result()

    # ── Operation routing ──────────────────────────────────────────────────
    if operation in ("default", "working"):
        result = _do_working_memory_op(ctx, model, state)
    elif operation == "session":
        result = _do_session_memory_op(ctx, model, state)
    elif operation == "episodic":
        result = _do_episodic_memory_op(ctx, model, state)
    elif operation == "profile":
        result = _do_user_profile_op(ctx, model, state)
    elif operation == "stale":
        result = _do_stale_memory_op(ctx, model, state)
    elif operation == "poisoning":
        result = _do_memory_poisoning_op(ctx, model, state)
    elif operation == "no_dump":
        result = _do_no_raw_conversation_op(ctx, model, state)
    elif operation == "budget":
        result = _do_retrieval_budget_op(ctx, model, state)
    else:
        ctx.mark_failed(f"Unknown operation: {operation}")
        return ctx.to_result()

    ctx.output = result
    ctx.snapshot_state(state)
    ctx.audit("memory_agent", "complete", outcome="success")
    return ctx.to_result()


def _do_working_memory_op(
    ctx: RunContext,
    model: ScriptedModel,
    state: dict[str, Any],
) -> dict[str, Any]:
    """Test working memory: write and read a temporary task."""
    ctx.record_model_call()

    # Create a working memory entry via model
    response = model.invoke(
        system_instruction="You are a task assistant. Store a working memory entry.",
        messages=[{"role": "user", "content": "__FIXTURE__:set_task"}],
    )
    ctx.record_model_call(tokens=response.usage.total_tokens)

    entry = MemoryEntry(
        id=f"wm_{uuid.uuid4().hex[:8]}",
        type="working",
        content="Current task: review pull request #142",
        confidence=0.95,
        timestamp=time.time(),
        ttl=WORKING_MEMORY_TTL,
    )

    # Write to working memory
    error = write_working_memory(ctx, state["working_memory"], "current_task", entry)
    if error:
        ctx.mark_failed(f"Working memory write failed: {error}")
        return {"status": "failed", "error": error}

    # Read back
    retrieved = read_working_memory(ctx, state["working_memory"], "current_task")
    if retrieved is None:
        ctx.mark_failed("Working memory read returned None")
        return {"status": "failed", "error": "entry not found"}

    return {
        "status": "success",
        "operation": "working_memory",
        "entry": entry.model_dump(),
        "retrieved": retrieved.model_dump(),
    }


def _do_session_memory_op(
    ctx: RunContext,
    model: ScriptedModel,
    state: dict[str, Any],
) -> dict[str, Any]:
    """Test session memory: write and read session-scoped data."""
    ctx.record_model_call()

    response = model.invoke(
        system_instruction="You are a task assistant. Store a session memory entry.",
        messages=[{"role": "user", "content": "__FIXTURE__:set_conversation_context"}],
    )
    ctx.record_model_call(tokens=response.usage.total_tokens)

    entry = MemoryEntry(
        id="sm_001",
        type="session",
        content="User is debugging database connection timeout",
        confidence=0.90,
        timestamp=time.time(),
        ttl=SESSION_MEMORY_TTL,
    )

    error = write_session_memory(ctx, state["session_memory"], "conversation_context", entry)
    if error:
        ctx.mark_failed(f"Session memory write failed: {error}")
        return {"status": "failed", "error": error}

    # Simulate a "second turn" — read the same entry
    retrieved = read_session_memory(ctx, state["session_memory"], "conversation_context")
    if retrieved is None:
        ctx.mark_failed("Session memory read across turns returned None")
        return {"status": "failed", "error": "entry not found across turns"}

    # Write a second entry to show persistence across multiple writes
    ctx.record_model_call()
    entry2 = MemoryEntry(
        id="sm_002",
        type="session",
        content="Modal dialog open: connection settings",
        confidence=0.75,
        timestamp=time.time(),
        ttl=SESSION_MEMORY_TTL,
    )
    error = write_session_memory(ctx, state["session_memory"], "ui_state", entry2)
    if error:
        ctx.mark_failed(f"Second session memory write failed: {error}")
        return {"status": "failed", "error": error}

    # Verify both entries available
    all_entries = {k: v.model_dump() for k, v in state["session_memory"].items()}

    return {
        "status": "success",
        "operation": "session_memory",
        "entries_count": len(state["session_memory"]),
        "entries": all_entries,
    }


def _do_episodic_memory_op(
    ctx: RunContext,
    model: ScriptedModel,
    state: dict[str, Any],
) -> dict[str, Any]:
    """Test episodic memory: write and retrieve past interactions."""
    ctx.record_model_call()

    # Write several past interactions
    past_entries = [
        MemoryEntry(
            id="em_001",
            type="episodic",
            content="User asked about PostgreSQL replication lag monitoring",
            confidence=0.88,
            timestamp=state.get("_ts", 0) or 1000,
            ttl=EPISODIC_MEMORY_TTL,
        ),
        MemoryEntry(
            id="em_002",
            type="episodic",
            content="User configured alert threshold for query latency at 500ms",
            confidence=0.92,
            timestamp=state.get("_ts", 0) or 1000,
            ttl=EPISODIC_MEMORY_TTL,
        ),
        MemoryEntry(
            id="em_003",
            type="episodic",
            content="User enabled slow query logging on production database",
            confidence=0.85,
            timestamp=state.get("_ts", 0) or 1000,
            ttl=EPISODIC_MEMORY_TTL,
        ),
    ]

    for entry in past_entries:
        error = write_episodic_memory(ctx, state["episodic_memory"], entry)
        if error:
            ctx.mark_failed(f"Episodic memory write failed: {error}")
            return {"status": "failed", "error": error}

    # Retrieve
    retrieved = read_episodic_memory(ctx, state["episodic_memory"])
    return {
        "status": "success",
        "operation": "episodic_memory",
        "entries_written": len(past_entries),
        "entries_retrieved": len(retrieved),
        "entries": [e.model_dump() for e in retrieved],
    }


def _do_user_profile_op(
    ctx: RunContext,
    model: ScriptedModel,
    state: dict[str, Any],
) -> dict[str, Any]:
    """Test user profile: load preferences, update with high confidence."""
    ctx.record_model_call()

    profile = UserProfile(
        preferences={
            "timezone": "UTC",
            "theme": "dark",
            "language": "en-US",
            "notifications_enabled": True,
        },
        history=[],
    )

    # Set a preference (no confidence threshold needed)
    set_preference(ctx, profile, "timezone", "America/New_York")
    set_preference(ctx, profile, "theme", "light")

    # Update profile with high-confidence entry
    high_conf_entry = MemoryEntry(
        id="ph_001",
        type="user_profile",
        content="User prefers concise technical answers",
        confidence=0.85,  # >= 0.7 threshold ✓
        timestamp=1000,
        ttl=None,
    )
    error = update_user_profile(ctx, profile, high_conf_entry)
    if error:
        ctx.mark_failed(f"High-confidence profile update failed: {error}")
        return {"status": "failed", "error": error}

    # Attempt low-confidence profile update (should be rejected)
    low_conf_entry = MemoryEntry(
        id="ph_002",
        type="user_profile",
        content="User wants all alerts at maximum severity",
        confidence=0.45,  # < 0.7 threshold ✗
        timestamp=1000,
        ttl=None,
    )
    error = update_user_profile(ctx, profile, low_conf_entry)
    if error is None:
        # This should have been rejected — fail if it wasn't
        ctx.mark_failed("Low-confidence profile update was accepted (should have been rejected)")
        return {"status": "failed", "error": "Low-confidence update accepted"}

    state["user_profile"] = profile

    return {
        "status": "success",
        "operation": "user_profile",
        "preferences": profile.preferences,
        "history_count": len(profile.history),
        "history": [e.model_dump() for e in profile.history],
        "rejected_low_confidence": True,
    }


def _do_stale_memory_op(
    ctx: RunContext,
    model: ScriptedModel,
    state: dict[str, Any],
) -> dict[str, Any]:
    """Test stale memory: expired entries are not returned."""
    import time

    now = time.time()

    # Write an expired entry (2 hours old, 1 hour TTL)
    stale_entry = MemoryEntry(
        id="stale_001",
        type="session",
        content="Expired session context from yesterday",
        confidence=0.80,
        timestamp=now - 7200,  # 2 hours ago
        ttl=3600.0,  # 1 hour TTL — expired
    )
    write_session_memory(ctx, state["session_memory"], "old_context", stale_entry)

    # Write a fresh entry (5 minutes old, 1 hour TTL)
    fresh_entry = MemoryEntry(
        id="stale_002",
        type="session",
        content="Current session context",
        confidence=0.80,
        timestamp=now - 300,  # 5 minutes ago
        ttl=3600.0,  # 1 hour TTL — still valid
    )
    write_session_memory(ctx, state["session_memory"], "current_context", fresh_entry)

    # Try to read stale entry — should return None
    retrieved_stale = read_session_memory(ctx, state["session_memory"], "old_context")
    stale_evicted = retrieved_stale is None

    # Read fresh entry — should work
    retrieved_fresh = read_session_memory(ctx, state["session_memory"], "current_context")
    fresh_available = retrieved_fresh is not None

    return {
        "status": "success",
        "operation": "stale_memory",
        "stale_evicted": stale_evicted,
        "fresh_available": fresh_available,
    }


def _do_memory_poisoning_op(
    ctx: RunContext,
    model: ScriptedModel,
    state: dict[str, Any],
) -> dict[str, Any]:
    """Test memory poisoning: low-confidence injections are rejected."""
    ctx.record_model_call()

    # Try to write a low-confidence session note (below 0.3 threshold)
    low_conf_note = MemoryEntry(
        id="low_001",
        type="session",
        content="User mentioned they prefer coffee over tea",
        confidence=0.15,  # Below minimum threshold (0.3)
        timestamp=1000,
        ttl=SESSION_MEMORY_TTL,
    )
    error = write_session_memory(ctx, state["session_memory"], "low_conf_note", low_conf_note)
    low_conf_rejected = error is not None

    # Try to write a session note with moderate confidence (above min, below profile)
    mod_conf_note = MemoryEntry(
        id="mid_001",
        type="session",
        content="User mentioned they use Python 3.12",
        confidence=0.55,  # Above min (0.3), below profile threshold (0.7)
        timestamp=1000,
        ttl=SESSION_MEMORY_TTL,
    )
    error = write_session_memory(ctx, state["session_memory"], "mod_conf_note", mod_conf_note)
    mod_conf_accepted = error is None

    return {
        "status": "success",
        "operation": "memory_poisoning",
        "low_confidence_rejected": low_conf_rejected,
        "moderate_confidence_accepted": mod_conf_accepted,
        "entries_in_session": len(state["session_memory"]),
    }


def _do_no_raw_conversation_op(
    ctx: RunContext,
    model: ScriptedModel,
    state: dict[str, Any],
) -> dict[str, Any]:
    """Test that raw conversation is not dumped into long-term memory."""
    ctx.record_model_call()

    # Attempt to write a raw conversation dump
    raw_entry = MemoryEntry(
        id="raw_001",
        type="raw_conversation",
        content=(
            "user: help me with my database\n"
            "assistant: sure, what's the issue?\n"
            "user: it's running slow\n"
            "assistant: let me check the query plans"
        ),
        confidence=0.95,
        timestamp=1000,
        ttl=None,
    )

    # Check if this would be a raw conversation dump
    is_raw_dump = check_raw_conversation_dumping(raw_entry.content, state["episodic_memory"])
    dump_prevented = False

    if is_raw_dump:
        # Reject the write — raw conversation should not go into episodic memory
        ctx.audit("memory", "raw_conversation_blocked", outcome="success")
        dump_prevented = True
    else:
        # Only write if it's not a raw dump
        write_episodic_memory(ctx, state["episodic_memory"], raw_entry)

    # Write a proper episodic entry (summarized, not raw)
    proper_entry = MemoryEntry(
        id="em_004",
        type="episodic",
        content="User is troubleshooting database performance issues with slow queries",
        confidence=0.88,
        timestamp=1000,
        ttl=None,
    )
    error = write_episodic_memory(ctx, state["episodic_memory"], proper_entry)
    proper_written = error is None

    return {
        "status": "success",
        "operation": "no_raw_conversation_dumping",
        "raw_dump_detected": is_raw_dump,
        "raw_dump_prevented": dump_prevented,
        "proper_entry_written": proper_written,
        "episodic_count": len(state["episodic_memory"]),
    }


def _do_retrieval_budget_op(
    ctx: RunContext,
    model: ScriptedModel,
    state: dict[str, Any],
) -> dict[str, Any]:
    """Test that retrieval budget limits the number of entries returned."""
    ctx.record_model_call()

    # Write 15 entries to episodic memory
    for i in range(15):
        entry = MemoryEntry(
            id=f"em_budget_{i:03d}",
            type="episodic",
            content=f"Test entry {i}: sample episodic memory content",
            confidence=0.80 + (i * 0.01),  # Slight variation
            timestamp=1000 + i,
            ttl=None,
        )
        write_episodic_memory(ctx, state["episodic_memory"], entry)

    # Retrieve with default budget
    retrieved = read_episodic_memory(ctx, state["episodic_memory"])
    budget_returned = len(retrieved)

    return {
        "status": "success",
        "operation": "retrieval_budget",
        "total_written": 15,
        "budget": RETRIEVAL_BUDGET,
        "returned": budget_returned,
        "budget_enforced": budget_returned <= RETRIEVAL_BUDGET,
    }
