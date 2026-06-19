"""Tests for Pattern 12: Shared Workspace / Blackboard.

Tests cover:
- 3 workers contribute claims, all appear on board
- Overwrite attempt is rejected (append-only)
- Version conflict triggers retry (optimistic locking)
- Each claim has author identity
- Synthesizer reads only accepted claims
- Concurrent write to same key detected (conflict detection)
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

from agent import run  # noqa: E402
from tools import add_claim, update_claim_status, get_accepted_claims  # noqa: E402

from adk_patterns.contracts import ExecutionStatus


def test_workers_contribute() -> None:
    """3 workers add claims, all appear on board."""
    result = run(scenario="success")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output
    board = state["evidence_board"]

    # All 3 claims should be present
    assert len(board) == 3
    assert "claim_001" in board
    assert "claim_002" in board
    assert "claim_003" in board

    # Verify claim content
    assert board["claim_001"]["author"] == "researcher_01"
    assert board["claim_002"]["author"] == "researcher_02"
    assert board["claim_003"]["author"] == "researcher_03"

    assert board["claim_001"]["confidence"] == 0.92
    assert board["claim_002"]["confidence"] == 0.98
    assert board["claim_003"]["confidence"] == 0.88

    # Verify budget constraints
    assert result.metrics["model_calls"] <= 4  # 3 workers + 1 synthesizer
    assert result.metrics["tool_calls"] == 0.0


def test_append_only() -> None:
    """Overwrite attempt rejected — append-only invariant."""
    result = run(scenario="append_only")

    assert result.status == ExecutionStatus.SUCCEEDED, f"Expected succeeded, got {result.status}: {result.failure_reason}"

    # The board should have exactly 1 claim (the overwrite was rejected)
    board = result.output["evidence_board"]
    assert len(board) == 1

    # Audit should show the overwrite was rejected
    events = result.audit_events
    rejections = [e for e in events if e.action == "overwrite_rejected"]
    assert len(rejections) >= 1, "Expected at least one overwrite_rejected audit event"


def test_optimistic_locking() -> None:
    """Version conflict triggers retry."""
    result = run(scenario="version_conflict")

    assert result.status == ExecutionStatus.SUCCEEDED, f"Expected succeeded, got {result.status}: {result.failure_reason}"

    board = result.output["evidence_board"]
    claim = board.get("claim_001", {})

    # After successful update, version should be 2 (incremented from 1)
    assert claim["version"] == 2, f"Expected version 2 after one update, got {claim.get('version')}"
    assert claim["status"] == "accepted"

    # Audit should show conflict was detected
    events = result.audit_events
    conflicts = [e for e in events if e.action == "version_conflict_detected"]
    assert len(conflicts) >= 1, "Expected at least one version_conflict_detected audit event"


def test_author_identity() -> None:
    """Each claim has correct author."""
    result = run(scenario="success")

    board = result.output["evidence_board"]

    assert board["claim_001"]["author"] == "researcher_01"
    assert board["claim_002"]["author"] == "researcher_02"
    assert board["claim_003"]["author"] == "researcher_03"

    # All authors must be distinct
    authors = [board[c]["author"] for c in board]
    assert len(set(authors)) == 3, f"Expected 3 distinct authors, got {authors}"


def test_synthesizer_reads_accepted_only() -> None:
    """Rejected claims excluded from synthesis."""
    result = run(scenario="synthesizer_rejected")

    assert result.status == ExecutionStatus.SUCCEEDED, f"Expected succeeded, got {result.status}: {result.failure_reason}"

    board = result.output["evidence_board"]
    synthesis = result.output["synthesizer_output"]

    # Verify claim statuses
    assert board["claim_001"]["status"] == "rejected"
    assert board["claim_002"]["status"] == "accepted"
    assert board["claim_003"]["status"] == "rejected"

    # Synthesizer should only see accepted claims
    assert synthesis["accepted_count"] == 1, f"Expected 1 accepted claim, got {synthesis['accepted_count']}"
    assert synthesis["claim_ids"] == ["claim_002"], f"Expected only claim_002, got {synthesis['claim_ids']}"


def test_conflict_detection() -> None:
    """Concurrent write to same key detected (direct tool-level test)."""
    # Start with an empty board
    board: dict = {}

    # Add a claim
    claim = {
        "id": "claim_X",
        "author": "researcher_X",
        "text": "Test claim for conflict detection.",
        "evidence": "Test evidence",
        "confidence": 0.5,
        "status": "pending",
        "version": 1,
    }
    board = add_claim(board, claim)

    # Simulate two concurrent readers getting version 1
    expected_version = 1

    # First writer succeeds
    board = update_claim_status(board, "claim_X", "accepted", expected_version=1)

    # Second writer with stale version should fail
    with pytest.raises(ValueError, match=r"Version conflict"):
        update_claim_status(board, "claim_X", "rejected", expected_version=1)

    # The claim should still be 'accepted' (first writer won)
    assert board["claim_X"]["status"] == "accepted"
    assert board["claim_X"]["version"] == 2  # Version incremented
