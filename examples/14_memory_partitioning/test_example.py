"""Tests for Pattern 14: Memory Partitioning.

Tests cover:
- Working memory — temporary data available during session
- Session memory — session-scoped data persists across turns within session
- Episodic memory — past interactions retrievable
- User profile — preferences loaded, updated with high confidence only
- Stale memory — expired entries not returned
- Memory poisoning — low-confidence injection rejected
- No raw conversation dumping — raw chat history not in long-term memory
- Retrieval budget — max entries returned respected
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Example directories starting with digits aren't valid Python packages.
# Add parent to path so we can import from them.
_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))

from agent import (  # noqa: E402
    run_memory_agent,
)

from adk_patterns.contracts import ExecutionStatus  # noqa: E402
from adk_patterns.models import ScriptedModel, structured_response  # noqa: E402
from adk_patterns.shared import run_scope  # noqa: E402


# ── Helper: build response sequences ────────────────────────────────────────


def _working_response() -> list:
    """Return a response sequence for working memory test."""
    return [
        structured_response({
            "id": "wm_001",
            "type": "working",
            "content": "Current task: review pull request #142",
            "confidence": 0.95,
            "timestamp": 1000,
            "ttl": 600.0,
        }),
    ]


def _session_response() -> list:
    """Return a response sequence for session memory test."""
    return [
        structured_response({
            "id": "sm_001",
            "type": "session",
            "content": "User is debugging database connection timeout",
            "confidence": 0.90,
            "timestamp": 1000,
            "ttl": 3600.0,
        }),
        structured_response({
            "id": "sm_002",
            "type": "session",
            "content": "Modal dialog open: connection settings",
            "confidence": 0.75,
            "timestamp": 1000,
            "ttl": 3600.0,
        }),
    ]


# ── Test: working memory ───────────────────────────────────────────────────


def test_working_memory() -> None:
    """Working memory stores temporary data available during session."""
    model = ScriptedModel()
    model.set_response_sequence(_working_response())

    with run_scope("memory-partitioning", "working", max_model_calls=3, max_tool_calls=5) as ctx:
        result = run_memory_agent(ctx, model, operation="working")

    assert result.status == ExecutionStatus.SUCCEEDED
    output = result.output
    assert output is not None
    assert output["status"] == "success"
    assert output["operation"] == "working_memory"
    assert output["entry"]["type"] == "working"
    assert output["entry"]["confidence"] >= 0.3
    assert output["retrieved"]["content"] == "Current task: review pull request #142"


def test_working_memory_state_keys() -> None:
    """State snapshot contains working_memory key."""
    model = ScriptedModel()
    model.set_response_sequence(_working_response())

    with run_scope("memory-partitioning", "state_keys", max_model_calls=3, max_tool_calls=5) as ctx:
        result = run_memory_agent(ctx, model, operation="working")

    state = result.state_snapshot
    assert "working_memory" in state


# ── Test: session memory ───────────────────────────────────────────────────


def test_session_memory() -> None:
    """Session-scoped data persists across turns within session."""
    model = ScriptedModel()
    model.set_response_sequence(_session_response())

    with run_scope("memory-partitioning", "session", max_model_calls=3, max_tool_calls=5) as ctx:
        result = run_memory_agent(ctx, model, operation="session")

    assert result.status == ExecutionStatus.SUCCEEDED
    output = result.output
    assert output is not None
    assert output["status"] == "success"
    assert output["operation"] == "session_memory"
    # Multiple entries should be available
    assert output["entries_count"] >= 2
    assert "conversation_context" in output["entries"]
    assert "ui_state" in output["entries"]


def test_session_memory_state_keys() -> None:
    """State snapshot contains session_memory key."""
    model = ScriptedModel()
    model.set_response_sequence(_session_response())

    with run_scope("memory-partitioning", "session_state", max_model_calls=3, max_tool_calls=5) as ctx:
        result = run_memory_agent(ctx, model, operation="session")

    state = result.state_snapshot
    assert "session_memory" in state


# ── Test: episodic memory ─────────────────────────────────────────────────


def test_episodic_memory() -> None:
    """Past interactions are retrievable from episodic memory."""
    model = ScriptedModel()

    with run_scope("memory-partitioning", "episodic", max_model_calls=3, max_tool_calls=5) as ctx:
        result = run_memory_agent(ctx, model, operation="episodic")

    assert result.status == ExecutionStatus.SUCCEEDED
    output = result.output
    assert output is not None
    assert output["status"] == "success"
    assert output["operation"] == "episodic_memory"
    assert output["entries_written"] == 3
    assert output["entries_retrieved"] >= 1
    assert output["entries_retrieved"] <= 10  # Budget


def test_episodic_memory_state_keys() -> None:
    """State snapshot contains episodic_memory key."""
    model = ScriptedModel()

    with run_scope("memory-partitioning", "episodic_state", max_model_calls=3, max_tool_calls=5) as ctx:
        result = run_memory_agent(ctx, model, operation="episodic")

    state = result.state_snapshot
    assert "episodic_memory" in state


# ── Test: user profile ────────────────────────────────────────────────────


def test_user_profile() -> None:
    """User preferences loaded, updated with high confidence only."""
    model = ScriptedModel()

    with run_scope("memory-partitioning", "profile", max_model_calls=3, max_tool_calls=5) as ctx:
        result = run_memory_agent(ctx, model, operation="profile")

    assert result.status == ExecutionStatus.SUCCEEDED
    output = result.output
    assert output is not None
    assert output["status"] == "success"
    assert output["operation"] == "user_profile"

    # Preferences should be loaded
    assert "timezone" in output["preferences"]
    assert "theme" in output["preferences"]

    # Only high-confidence entries in history
    assert output["history_count"] == 1  # Only the high-confidence one

    # High-confidence entry was accepted
    assert output["history"][0]["confidence"] >= 0.7

    # Low-confidence update was rejected
    assert output["rejected_low_confidence"] is True


def test_user_profile_state_keys() -> None:
    """State snapshot contains user_profile key."""
    model = ScriptedModel()

    with run_scope("memory-partitioning", "profile_state", max_model_calls=3, max_tool_calls=5) as ctx:
        result = run_memory_agent(ctx, model, operation="profile")

    state = result.state_snapshot
    assert "user_profile" in state


# ── Test: stale memory ─────────────────────────────────────────────────────


def test_stale_memory() -> None:
    """Expired entries are not returned from memory stores."""
    model = ScriptedModel()

    with run_scope("memory-partitioning", "stale", max_model_calls=3, max_tool_calls=5) as ctx:
        result = run_memory_agent(ctx, model, operation="stale")

    assert result.status == ExecutionStatus.SUCCEEDED
    output = result.output
    assert output is not None
    assert output["status"] == "success"
    assert output["operation"] == "stale_memory"

    # Stale entry should be evicted
    assert output["stale_evicted"] is True

    # Fresh entry should still be available
    assert output["fresh_available"] is True


# ── Test: memory poisoning ─────────────────────────────────────────────────


def test_memory_poisoning() -> None:
    """Low-confidence injections are rejected."""
    model = ScriptedModel()

    with run_scope("memory-partitioning", "poisoning", max_model_calls=3, max_tool_calls=5) as ctx:
        result = run_memory_agent(ctx, model, operation="poisoning")

    assert result.status == ExecutionStatus.SUCCEEDED
    output = result.output
    assert output is not None
    assert output["status"] == "success"
    assert output["operation"] == "memory_poisoning"

    # Low-confidence entry should be rejected
    assert output["low_confidence_rejected"] is True

    # Moderate-confidence entry should be accepted
    assert output["moderate_confidence_accepted"] is True

    # Session should have only the moderate-confidence entry
    assert output["entries_in_session"] == 1


# ── Test: no raw conversation dumping ──────────────────────────────────────


def test_no_raw_conversation_dumping() -> None:
    """Raw chat history is not dumped into long-term memory."""
    model = ScriptedModel()

    with run_scope("memory-partitioning", "no_dump", max_model_calls=3, max_tool_calls=5) as ctx:
        result = run_memory_agent(ctx, model, operation="no_dump")

    assert result.status == ExecutionStatus.SUCCEEDED
    output = result.output
    assert output is not None
    assert output["status"] == "success"
    assert output["operation"] == "no_raw_conversation_dumping"

    # Raw dump should be detected and prevented
    assert output["raw_dump_detected"] is True
    assert output["raw_dump_prevented"] is True

    # Proper entry should still be written
    assert output["proper_entry_written"] is True

    # Episodic memory should have only the proper entry, not the raw dump
    assert output["episodic_count"] == 1  # Only the proper one


# ── Test: retrieval budget ────────────────────────────────────────────────


def test_retrieval_budget() -> None:
    """Max entries returned is respected (RETRIEVAL_BUDGET = 10)."""
    model = ScriptedModel()

    with run_scope("memory-partitioning", "budget", max_model_calls=3, max_tool_calls=5) as ctx:
        result = run_memory_agent(ctx, model, operation="budget")

    assert result.status == ExecutionStatus.SUCCEEDED
    output = result.output
    assert output is not None
    assert output["status"] == "success"
    assert output["operation"] == "retrieval_budget"

    # 15 entries written, budget is 10
    assert output["total_written"] == 15

    # Budget should be enforced
    assert output["budget_enforced"] is True
    assert output["returned"] <= output["budget"]
    assert output["returned"] == 10  # Exactly budget


# ── Test: budget enforcement ───────────────────────────────────────────────


def test_budget_max_model_calls() -> None:
    """Enforce max_model_calls=3 — exactly 3 calls max."""
    model = ScriptedModel()
    model.set_repeat_response(structured_response({
        "id": "wm_001",
        "type": "working",
        "content": "Test entry",
        "confidence": 0.95,
        "timestamp": 1000,
        "ttl": 600.0,
    }))

    with run_scope("memory-partitioning", "budget_check", max_model_calls=3, max_tool_calls=5) as ctx:
        result = run_memory_agent(ctx, model, operation="working")

    assert result.metrics["model_calls"] <= 3.0


# ── Test: audit events ─────────────────────────────────────────────────────


def test_audit_events_present() -> None:
    """Audit events are recorded for memory operations."""
    model = ScriptedModel()
    model.set_response_sequence(_working_response())

    with run_scope("memory-partitioning", "audit", max_model_calls=3, max_tool_calls=5) as ctx:
        result = run_memory_agent(ctx, model, operation="working")

    assert len(result.audit_events) >= 3
    memory_events = [e for e in result.audit_events if e.actor == "memory"]
    assert len(memory_events) >= 2
