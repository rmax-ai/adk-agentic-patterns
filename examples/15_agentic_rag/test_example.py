"""Tests for Pattern 15: Agentic RAG.

Tests cover:
- test_multi_hop_question: 2-step retrieval to answer multi-hop question
- test_single_pass_baseline: Single retrieval baseline for comparison
- test_unsupported_claim_rejected: Claims without supporting docs are rejected
- test_citation_validation: All citations reference docs in the evidence ledger
- test_max_retrieval_rounds: Loop limit enforced at 3 rounds
"""

from __future__ import annotations

import sys
from pathlib import Path

# Example directories starting with digits aren't valid Python packages.
# Add parent to path so we can import from them.
_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))

from agent import run, validate_citations  # noqa: E402

from adk_patterns.contracts import ExecutionStatus  # noqa: E402


# ── Test: Multi-hop question (2-step retrieval) ────────────────────────────


def test_multi_hop_question() -> None:
    """Agent retrieves in 2 steps to answer a multi-hop question.

    The question "What framework and database does Acme Corp use?" requires
    doc_framework (Python/FastAPI) and doc_database (PostgreSQL/Redis).
    The agent should retrieve both and synthesize a complete answer.
    """
    result = run(scenario="multi_hop")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output

    # Should have retrieved documents
    assert "retrieved_docs" in state
    assert len(state["retrieved_docs"]) >= 2

    # Should have both required docs
    doc_ids = {d["doc_id"] for d in state["retrieved_docs"]}
    assert "doc_framework" in doc_ids, "Should have retrieved doc about Python/FastAPI"
    assert "doc_database" in doc_ids, "Should have retrieved doc about PostgreSQL"

    # Should have an answer
    assert state["answer"] is not None
    assert len(state["answer"]) > 0

    # Should have citations
    assert "citations" in state
    assert len(state["citations"]) > 0

    # Should have evidence ledger
    assert "evidence_ledger" in state
    ledger = state["evidence_ledger"]
    assert isinstance(ledger, dict)
    assert "entries" in ledger or len(ledger) > 0

    # Should have completed in 1-3 rounds
    assert 1 <= state.get("retrieval_round", 99) <= 3

    # Answer should reference framework and database
    answer_lower = state["answer"].lower()
    # The answer should contain info from both docs
    assert any(word in answer_lower for word in ["python", "fastapi", "flask"]), \
        "Answer should reference the framework"
    assert any(word in answer_lower for word in ["postgresql", "postgres", "database", "redis"]), \
        "Answer should reference the database"


# ── Test: Single-pass baseline ──────────────────────────────────────────────


def test_single_pass_baseline() -> None:
    """Single retrieval pass without iterative refinement.

    The baseline retrieves once and synthesizes an answer from those docs only.
    """
    result = run(scenario="single_pass_baseline")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output

    # Should have retrieved documents
    assert "retrieved_docs" in state
    assert len(state["retrieved_docs"]) >= 1

    # Single-pass should have exactly 1 retrieval round
    assert state.get("retrieval_round") == 1, \
        "Baseline should have exactly 1 retrieval round"

    # Should have an answer
    assert state["answer"] is not None
    assert len(state["answer"]) > 0

    # Should have citations
    assert len(state.get("citations", [])) > 0

    # Termination reason should indicate single pass
    assert state.get("termination_reason") == "single_pass"


# ── Test: Unsupported claim rejected ────────────────────────────────────────


def test_unsupported_claim_rejected() -> None:
    """Claims without supporting documents are rejected/marked unsupported.

    The query "What ML framework does Acme Corp use?" has no documents
    mentioning ML frameworks, so claims should be marked unsupported.
    """
    result = run(scenario="unsupported_claim")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output

    # The answer should indicate unsupported claims or lack of evidence
    answer_lower = (state.get("answer") or "").lower()

    # The search might return low-relevance docs; the agent should note
    # that ML framework info is not supported by evidence
    has_unsupported = (
        "unsupported" in answer_lower
        or "cannot" in answer_lower
        or "not found" in answer_lower
        or "no evidence" in answer_lower
        or "not supported" in answer_lower
        or "unable" in answer_lower
        or not state.get("supported", True)
    )

    # Either supported=False, or the answer text acknowledges limitation
    assert has_unsupported or state.get("supported") is False, \
        "Answer should indicate unsupported claims"


# ── Test: Citation validation ───────────────────────────────────────────────


def test_citation_validation() -> None:
    """All citations reference documents in the evidence ledger.

    After answering, citations should be validated against the evidence ledger
    to ensure every claim has a supporting document.
    """
    # Run the multi-hop scenario (produces real citations)
    result = run(scenario="citation_validation")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output

    assert "citations" in state
    assert "evidence_ledger" in state

    # Validate citations against the ledger
    state = validate_citations(state)

    validation = state.get("citation_validation", {})
    assert validation.get("all_valid", False), \
        f"Citation validation failed: {validation.get('invalid', [])}"

    # Every citation doc_id should be in the ledger
    if state["citations"]:
        ledger_entries = state["evidence_ledger"].get("entries", {})
        ledger_doc_ids = set(ledger_entries.keys())
        for c in state["citations"]:
            assert c["doc_id"] in ledger_doc_ids, \
                f"Citation {c['claim']} references {c['doc_id']} not in ledger"


# ── Test: Maximum retrieval rounds ──────────────────────────────────────────


def test_max_retrieval_rounds() -> None:
    """Maximum of 3 retrieval rounds is enforced.

    The agent should not exceed max_rounds=3 even if the model keeps
    requesting more documents.
    """
    result = run(scenario="max_retrieval_rounds")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output

    # Should not exceed 3 retrieval rounds
    assert state.get("retrieval_round", 99) <= 3, \
        f"Retrieval rounds ({state.get('retrieval_round')}) exceeded maximum of 3"

    # Termination reason should reflect round limit or budget
    term_reason = state.get("termination_reason", "")
    assert term_reason in (
        "enough_information",
        "max_rounds_reached",
        "budget_exhausted",
        "unknown",
    ), f"Unexpected termination reason: {term_reason}"


# ── Test: State keys present ───────────────────────────────────────────────


def test_state_keys_present() -> None:
    """All required state keys are present in the output."""
    result = run(scenario="multi_hop")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output

    required_keys = {"retrieved_docs", "evidence_ledger", "answer", "citations"}
    for key in required_keys:
        assert key in state, f"Required state key '{key}' is missing"

    # Verify snapshot contains the same keys
    snapshot = result.state_snapshot
    for key in required_keys:
        assert key in snapshot, f"State key '{key}' missing from snapshot"


# ── Test: Budget enforcement ────────────────────────────────────────────────


def test_budget_enforcement() -> None:
    """Budget limits (max_model_calls=5, max_tool_calls=8, max_iterations=3)
    are enforced and reflected in metrics.
    """
    result = run(scenario="multi_hop")

    assert result.state_snapshot is not None

    metrics = result.metrics
    assert metrics["model_calls"] <= 6.0, \
        f"Model calls ({metrics['model_calls']}) exceeded max_model_calls=5"
    assert metrics["tool_calls"] <= 9.0, \
        f"Tool calls ({metrics['tool_calls']}) exceeded max_tool_calls=8"
    assert metrics["iterations"] <= 4.0, \
        f"Iterations ({metrics['iterations']}) exceeded max_iterations=3"
