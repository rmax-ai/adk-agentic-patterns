"""Test fixtures for Pattern 14: Memory Partitioning.

ScriptedModel responses for deterministic testing of memory operations.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Add example dir to path for sibling imports
_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))

from contracts import MemoryEntry, UserProfile  # noqa: E402

# ── Working memory fixtures ────────────────────────────────────────────────

WORKING_MEMORY_RESPONSES = {
    "set_task": MemoryEntry(
        id="wm_001",
        type="working",
        content="Current task: review pull request #142",
        confidence=0.95,
        timestamp=time.time(),
        ttl=600.0,
    ),
    "get_task": MemoryEntry(
        id="wm_001",
        type="working",
        content="Current task: review pull request #142",
        confidence=0.95,
        timestamp=time.time(),
        ttl=600.0,
    ),
    "set_note": MemoryEntry(
        id="wm_002",
        type="working",
        content="Note: waiting for CI build to complete",
        confidence=0.85,
        timestamp=time.time(),
        ttl=600.0,
    ),
}

# ── Session memory fixtures ────────────────────────────────────────────────

SESSION_MEMORY_RESPONSES = {
    "set_conversation_context": MemoryEntry(
        id="sm_001",
        type="session",
        content="User is debugging database connection timeout",
        confidence=0.90,
        timestamp=time.time(),
        ttl=3600.0,
    ),
    "get_conversation_context": MemoryEntry(
        id="sm_001",
        type="session",
        content="User is debugging database connection timeout",
        confidence=0.90,
        timestamp=time.time(),
        ttl=3600.0,
    ),
    "set_ui_state": MemoryEntry(
        id="sm_002",
        type="session",
        content="Modal dialog open: connection settings",
        confidence=0.75,
        timestamp=time.time(),
        ttl=3600.0,
    ),
}

# ── Episodic memory fixtures ───────────────────────────────────────────────

EPISODIC_MEMORY_RESPONSES = {
    "past_interaction_1": MemoryEntry(
        id="em_001",
        type="episodic",
        content="User asked about PostgreSQL replication lag monitoring",
        confidence=0.88,
        timestamp=time.time() - 86400,  # 1 day ago
        ttl=None,
    ),
    "past_interaction_2": MemoryEntry(
        id="em_002",
        type="episodic",
        content="User configured alert threshold for query latency at 500ms",
        confidence=0.92,
        timestamp=time.time() - 43200,  # 12 hours ago
        ttl=None,
    ),
    "past_interaction_3": MemoryEntry(
        id="em_003",
        type="episodic",
        content="User enabled slow query logging on production database",
        confidence=0.85,
        timestamp=time.time() - 21600,  # 6 hours ago
        ttl=None,
    ),
}

# ── User profile fixtures ──────────────────────────────────────────────────

PROFILE_FIXTURES = {
    "default_profile": UserProfile(
        preferences={
            "timezone": "UTC",
            "theme": "dark",
            "language": "en-US",
            "notifications_enabled": True,
        },
        history=[],
    ),
    "loaded_profile": UserProfile(
        preferences={
            "timezone": "America/New_York",
            "theme": "light",
            "language": "en-US",
            "notifications_enabled": False,
            "preferred_model": "gemini-pro",
        },
        history=[
            MemoryEntry(
                id="ph_001",
                type="user_profile",
                content="User prefers concise technical answers",
                confidence=0.85,
                timestamp=time.time() - 172800,  # 2 days ago
                ttl=None,
            ),
        ],
    ),
}

# ── Low-confidence / poisoning fixtures ────────────────────────────────────

POISONING_FIXTURES = {
    "low_confidence_note": MemoryEntry(
        id="low_001",
        type="session",
        content="User mentioned they prefer coffee over tea",
        confidence=0.15,  # Below minimum threshold
        timestamp=time.time(),
        ttl=3600.0,
    ),
    "low_confidence_profile_update": MemoryEntry(
        id="low_p_001",
        type="user_profile",
        content="User wants all alerts at maximum severity",
        confidence=0.45,  # Below profile threshold (0.7), above min (0.3)
        timestamp=time.time(),
        ttl=None,
    ),
    "raw_conversation_dump": MemoryEntry(
        id="raw_001",
        type="raw_conversation",
        content="user: help me with my database\nassistant: sure, what's the issue?\nuser: it's running slow\nassistant: let me check the query plans",
        confidence=0.95,
        timestamp=time.time(),
        ttl=None,
    ),
}

# ── Stale memory fixtures ──────────────────────────────────────────────────

STALE_FIXTURES = {
    "old_session_entry": MemoryEntry(
        id="stale_001",
        type="session",
        content="Expired session context from yesterday",
        confidence=0.80,
        timestamp=time.time() - 7200,  # 2 hours ago (past 1hr TTL)
        ttl=3600.0,
    ),
    "fresh_session_entry": MemoryEntry(
        id="stale_002",
        type="session",
        content="Current session context",
        confidence=0.80,
        timestamp=time.time() - 300,  # 5 minutes ago
        ttl=3600.0,
    ),
}
