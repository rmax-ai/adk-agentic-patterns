"""Blackboard tools for Pattern 12: Shared Workspace.

Pure Python data-structure operations on the evidence_board dict.
- add_claim: append-only; rejects overwrites of existing claim IDs.
- update_claim_status: optimistic locking via version check.
- read_board: returns all claims.
- get_accepted_claims: returns only accepted claims for the synthesizer.
"""

from __future__ import annotations

import copy
from typing import Any

from contracts import Claim


def add_claim(board: dict[str, dict[str, Any]], claim: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Add a new claim to the evidence board (append-only).

    Raises ValueError if a claim with the same ID already exists.
    Returns a new board dict (immutable update).
    """
    cid = claim.get("id", "")
    if not cid:
        raise ValueError("Claim must have an 'id' field")

    if cid in board:
        raise ValueError(f"Claim '{cid}' already exists on the board — append-only, no overwrites allowed")

    new_board = dict(board)
    new_board[cid] = dict(claim)
    return new_board


def update_claim_status(
    board: dict[str, dict[str, Any]],
    claim_id: str,
    new_status: str,
    expected_version: int,
) -> dict[str, dict[str, Any]]:
    """Update a claim's status with optimistic locking (version check).

    Raises ValueError if:
      - claim_id not found
      - version mismatch (conflict detected)
      - new_status not in ('pending', 'accepted', 'rejected')

    Returns a new board dict with the updated claim.
    """
    if claim_id not in board:
        raise ValueError(f"Claim '{claim_id}' not found on the board")

    if new_status not in ("pending", "accepted", "rejected"):
        raise ValueError(f"Invalid status '{new_status}'; must be pending, accepted, or rejected")

    current = board[claim_id]
    if current["version"] != expected_version:
        raise ValueError(
            f"Version conflict for claim '{claim_id}': "
            f"expected version {expected_version}, "
            f"current version {current['version']}"
        )

    new_board = dict(board)
    updated = dict(current)
    updated["status"] = new_status
    updated["version"] = current["version"] + 1
    new_board[claim_id] = updated
    return new_board


def read_board(board: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Return all claims sorted by claim ID."""
    return [board[k] for k in sorted(board.keys())]


def get_accepted_claims(board: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Return only accepted claims, sorted by confidence descending."""
    accepted = [c for c in board.values() if c.get("status") == "accepted"]
    return sorted(accepted, key=lambda c: c.get("confidence", 0.0), reverse=True)


def synthesize_accepted_claims(board: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Synthesize a summary from accepted claims only.

    Returns a SynthesizerOutput-like dict.
    """
    accepted = get_accepted_claims(board)
    if not accepted:
        return {"summary": "No accepted claims to synthesize.", "accepted_count": 0, "claim_ids": []}

    claim_ids = [c["id"] for c in accepted]
    # Build a simple summary from accepted claim texts
    total_confidence = sum(c.get("confidence", 0.0) for c in accepted)
    avg_confidence = total_confidence / len(accepted)

    lines = [f"- {c['text']} (confidence: {c['confidence']:.2f}, author: {c['author']})" for c in accepted]
    summary = (
        f"Synthesized {len(accepted)} accepted claims "
        f"(avg confidence: {avg_confidence:.2f}):\n" + "\n".join(lines)
    )

    return {
        "summary": summary,
        "accepted_count": len(accepted),
        "claim_ids": claim_ids,
    }
