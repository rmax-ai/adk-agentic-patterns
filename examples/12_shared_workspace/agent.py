"""Pattern 12: Shared Workspace / Blackboard.

Scenario: Multiple research workers contribute claims to a shared evidence
board (append-only). Each claim carries author identity, evidence,
confidence, and a version field for optimistic locking. A synthesizer
reads only accepted claims to produce a final summary.

Demonstrates:
- Append-only workspace with versioned entries
- Optimistic locking (compare-and-swap) for status updates
- Conflict detection for concurrent writes to the same key
- Author identity preservation
- Synthesizer isolation (reads only accepted claims)

State keys: evidence_board{}, synthesizer_output
Contracts: Claim(id, author, text, evidence, confidence, status, version)
Budget: max_model_calls=3, max_tool_calls=5
"""

from __future__ import annotations

import asyncio
import copy
import sys
from pathlib import Path
from typing import Any

# Ensure this example directory is on sys.path for absolute imports
_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))

from adk_patterns.contracts import ExecutionStatus, PatternRunResult
from adk_patterns.config import Config
from adk_patterns.models import ScriptedModel, structured_response
from adk_patterns.shared import RunContext, run_scope

from contracts import Claim, EvidenceBoard, SynthesizerOutput  # noqa: E402
from fixtures import FIXTURES  # noqa: E402
from tools import (  # noqa: E402
    add_claim,
    get_accepted_claims,
    read_board,
    synthesize_accepted_claims,
    update_claim_status,
)

# -- Constants ----------------------------------------------------------------

PATTERN_NAME = "shared-workspace"
MAX_MODEL_CALLS = 3
MAX_TOOL_CALLS = 5

# -- Worker functions (async coroutines) --------------------------------------


async def _worker_contribute(
    ctx: RunContext,
    model: ScriptedModel,
    worker_name: str,
    fixture_key: str,
    board: EvidenceBoard,
) -> tuple[EvidenceBoard, Claim]:
    """A research worker contributes a claim to the shared evidence board.

    The worker invokes the model to generate a claim, then adds it to the
    board using the append-only add_claim tool.

    Returns the updated board and the new claim.
    """
    ctx.audit("worker", "contribute", resource=worker_name)

    response = model.invoke(
        system_instruction=f"You are researcher {worker_name}. Contribute a research claim to the evidence board.",
        messages=[{"role": "user", "content": f"__FIXTURE__:{fixture_key} Contribute claim as {worker_name}"}],
    )

    ctx.record_model_call(tokens=response.usage.total_tokens)
    ctx.audit("worker", "model_response", resource=worker_name, outcome="success")

    if response.structured_output:
        claim_data = response.structured_output
    else:
        fixture = FIXTURES.get(fixture_key)
        if fixture is None:
            raise ValueError(f"No fixture for key: {fixture_key}")
        claim_data = fixture.structured_output or {}

    # Validate claim
    claim = Claim(**claim_data)

    # Append-only add to board
    updated_board = add_claim(board, claim.model_dump())

    ctx.audit("board", "add_claim", resource=claim.id, metadata={"author": claim.author, "status": claim.status})
    ctx.snapshot_state({"evidence_board": updated_board, "last_claim_id": claim.id})

    return updated_board, claim


async def _synthesizer_gather(
    ctx: RunContext,
    model: ScriptedModel,
    board: EvidenceBoard,
    fixture_key: str = "synthesizer_output",
) -> SynthesizerOutput:
    """Synthesizer reads only accepted claims from the board.

    If there are no accepted claims, returns an empty summary.
    Otherwise invokes the model for a structured synthesis.
    """
    accepted = get_accepted_claims(board)
    if not accepted:
        ctx.audit("synthesizer", "no_accepted_claims", outcome="skipped")
        return SynthesizerOutput(
            summary="No accepted claims to synthesize.",
            accepted_count=0,
            claim_ids=[],
        )

    ctx.audit("synthesizer", "model_call", metadata={"accepted_count": len(accepted)})

    response = model.invoke(
        system_instruction="Synthesize the accepted research claims into a coherent summary.",
        messages=[
            {
                "role": "user",
                "content": f"__FIXTURE__:{fixture_key} Synthesize accepted claims: {accepted}",
            }
        ],
    )

    ctx.record_model_call(tokens=response.usage.total_tokens)
    ctx.audit("synthesizer", "model_response", outcome="success")

    if response.structured_output:
        synth = SynthesizerOutput(**response.structured_output)
        # Validate: the model's output must match the actual board state
        actual_accepted = get_accepted_claims(board)
        if len(actual_accepted) != synth.accepted_count:
            ctx.audit("synthesizer", "board_mismatch", outcome="info",
                      metadata={"model_said": synth.accepted_count, "board_has": len(actual_accepted)})
            # Fall back to board-based synthesis
            board_result = synthesize_accepted_claims(board)
            return SynthesizerOutput(**board_result)
        return synth

    # Fallback: build from the board directly
    ctx.audit("synthesizer", "using_board_fallback", outcome="info")
    board_result = synthesize_accepted_claims(board)
    return SynthesizerOutput(**board_result)


# -- Main run entry point -----------------------------------------------------


async def _run_async(
    ctx: RunContext,
    model: ScriptedModel,
    board: EvidenceBoard | None = None,
    scenario: str = "success",
) -> EvidenceBoard:
    """Run the shared workspace pattern.

    Args:
        ctx: Run context for audit and budget tracking.
        model: Scripted model with pre-registered fixtures.
        board: Optional initial board (used for conflict tests).
        scenario: Test scenario name.

    Returns:
        Final evidence board after all contributions and synthesis.
    """
    current_board: EvidenceBoard = copy.deepcopy(board) if board else {}

    if scenario == "success":
        # 3 workers contribute claims
        worker_fixtures = [
            ("researcher_01", "claim_researcher_01"),
            ("researcher_02", "claim_researcher_02"),
            ("researcher_03", "claim_researcher_03"),
        ]

        for worker_name, fixture_key in worker_fixtures:
            current_board, _ = await _worker_contribute(ctx, model, worker_name, fixture_key, current_board)

        # Synthesizer reads accepted claims
        # First, accept all claims (optimistic locking)
        for claim_id in list(current_board.keys()):
            current_board = update_claim_status(current_board, claim_id, "accepted", expected_version=1)

        synthesis = await _synthesizer_gather(ctx, model, current_board)

        # Record state
        state = {
            "evidence_board": current_board,
            "synthesizer_output": synthesis.model_dump(),
        }
        ctx.snapshot_state(state)
        ctx.output = state

    elif scenario == "append_only":
        # Add one claim, then attempt to overwrite it (should fail)
        current_board, claim = await _worker_contribute(
            ctx, model, "researcher_01", "claim_researcher_01", current_board
        )

        # Attempt overwrite (same claim ID)
        try:
            duplicate = dict(claim.model_dump())
            current_board = add_claim(current_board, duplicate)
            # If we get here, the overwrite wasn't blocked
            ctx.mark_failed("Overwrite was not rejected — append-only invariant broken")
        except ValueError as e:
            # Expected: append-only prevents overwrite
            ctx.audit("board", "overwrite_rejected", outcome="success", metadata={"error": str(e)})

        state = {
            "evidence_board": current_board,
            "synthesizer_output": {"summary": "Overwrite test completed.", "accepted_count": 0, "claim_ids": []},
        }
        ctx.snapshot_state(state)
        ctx.output = state

    elif scenario == "version_conflict":
        # Add a claim, then simulate a version conflict
        current_board, claim = await _worker_contribute(
            ctx, model, "researcher_01", "claim_researcher_01", current_board
        )

        claim_id = claim.id
        original_version = claim.version

        # First update (succeeds)
        current_board = update_claim_status(current_board, claim_id, "accepted", expected_version=original_version)

        # Second update with stale version (should fail)
        try:
            current_board = update_claim_status(current_board, claim_id, "rejected", expected_version=original_version)
            ctx.mark_failed("Version conflict was not detected — optimistic locking broken")
        except ValueError as e:
            ctx.audit("board", "version_conflict_detected", outcome="success", metadata={"error": str(e)})

        state = {
            "evidence_board": current_board,
            "synthesizer_output": {"summary": "Version conflict test completed.", "accepted_count": 0, "claim_ids": []},
        }
        ctx.snapshot_state(state)
        ctx.output = state

    elif scenario == "synthesizer_rejected":
        # Add 3 claims, accept claim_002 only, reject the rest
        worker_fixtures = [
            ("researcher_01", "claim_researcher_01"),
            ("researcher_02", "claim_researcher_02"),
            ("researcher_03", "claim_researcher_03"),
        ]
        for worker_name, fixture_key in worker_fixtures:
            current_board, _ = await _worker_contribute(ctx, model, worker_name, fixture_key, current_board)

        # Accept only claim_002
        current_board = update_claim_status(current_board, "claim_002", "accepted", expected_version=1)
        # Reject the others
        current_board = update_claim_status(current_board, "claim_001", "rejected", expected_version=1)
        current_board = update_claim_status(current_board, "claim_003", "rejected", expected_version=1)

        # Synthesizer should see only claim_002
        synthesis = await _synthesizer_gather(ctx, model, current_board)

        if synthesis.accepted_count != 1:
            ctx.mark_failed(
                f"Synthesizer read {synthesis.accepted_count} claims, expected 1 — "
                f"rejected claims were not excluded"
            )

        state = {
            "evidence_board": current_board,
            "synthesizer_output": synthesis.model_dump(),
        }
        ctx.snapshot_state(state)
        ctx.output = state

    else:
        raise ValueError(f"Unknown scenario: {scenario}")

    return current_board


# -- Fixture registration -----------------------------------------------------


def _register_fixtures(model: ScriptedModel) -> None:
    """Register fixture responses on the scripted model."""
    for key, value in FIXTURES.items():
        model.register_fixture(key, value)


# -- Public API ----------------------------------------------------------------


def run(
    config: Config | None = None,
    scenario: str = "success",
) -> PatternRunResult:
    """Entry point for CLI and tests.

    Args:
        config: Application configuration (uses defaults if None).
        scenario: Test scenario ('success', 'append_only', 'version_conflict',
                  'synthesizer_rejected').

    Returns:
        PatternRunResult with evidence board and synthesis outputs.
    """
    model = ScriptedModel()
    _register_fixtures(model)

    with run_scope(
        PATTERN_NAME,
        scenario,
        max_model_calls=MAX_MODEL_CALLS,
        max_tool_calls=MAX_TOOL_CALLS,
    ) as ctx:
        try:
            asyncio.run(_run_async(ctx, model, scenario=scenario))
        except Exception as e:
            ctx.mark_failed(str(e))

    return ctx.to_result()


def main(config: Config | None = None, scenario: str = "success") -> PatternRunResult:
    """Standard entry point called by CLI.

    Usage:
        uv run python -m examples.12_shared_workspace.run
        uv run python -m examples.12_shared_workspace.run --scenario append_only
    """
    return run(config=config, scenario=scenario)
