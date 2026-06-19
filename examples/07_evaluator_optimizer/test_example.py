"""Tests for Pattern 07: Evaluator-Optimizer.

Tests cover:
- Converging to threshold score (overall >= 0.8)
- Max iterations (4) reached without converging
- No-progress detection (score flat for 2 consecutive iterations)
- Evaluator failure fallback (uses last good draft)
- Independent vs same-model evaluator comparison
- Localized per-section feedback
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
    CHECKER_FIXTURES,
    FLAT_CHECKER_FIXTURES,
    FLAT_MAKER_FIXTURES,
    INDEPENDENT_CHECKER,
    MAKER_FIXTURES,
    Proposal,
    RubricScores,
    _register_all_fixtures,
    evaluate_proposal,
    run_evaluator_optimizer,
)

from adk_patterns.contracts import ExecutionStatus  # noqa: E402
from adk_patterns.models import ScriptedModel, structured_response  # noqa: E402
from adk_patterns.shared import run_scope  # noqa: E402


# ── Helper: build response sequences ────────────────────────────────────────


def _converge_sequence() -> list:
    """Scores: 0.53 → 0.63 → 0.82 (threshold met on 3rd check → SUCCEEDED)."""
    return [
        structured_response(MAKER_FIXTURES["maker_v1"]),
        structured_response(CHECKER_FIXTURES["checker_v1"]),  # 0.53
        structured_response(MAKER_FIXTURES["maker_v2"]),
        structured_response(CHECKER_FIXTURES["checker_v2"]),  # 0.63
        structured_response(MAKER_FIXTURES["maker_v3"]),
        structured_response(CHECKER_FIXTURES["checker_v3"]),  # 0.82 >= 0.8 ✓
    ]


def _max_iter_sequence() -> list:
    """Scores: 0.53 → 0.54 → 0.55 → 0.56 — all < 0.8, slightly increasing.

    Uses custom eval dicts to avoid triggering no-progress detection.
    """
    low_scores = [
        {"clarity": 0.50, "completeness": 0.50, "feasibility": 0.55, "risk": 0.50, "overall": s, "feedback": ["ok"]}
        for s in [0.53, 0.54, 0.55, 0.56]
    ]
    return [
        structured_response(MAKER_FIXTURES["maker_v1"]),
        structured_response(low_scores[0]),  # 0.53
        structured_response(MAKER_FIXTURES["maker_v2"]),
        structured_response(low_scores[1]),  # 0.54
        structured_response(MAKER_FIXTURES["maker_v3"]),
        structured_response(low_scores[2]),  # 0.55
        structured_response(MAKER_FIXTURES["maker_v4"]),
        structured_response(low_scores[3]),  # 0.56 — still < 0.8, 4 iters done
    ]


def _no_progress_sequence() -> list:
    """All 3 evaluations return the same score (0.58), flat for 2+ iterations."""
    return [
        structured_response(FLAT_MAKER_FIXTURES["flat_v1"]),
        structured_response(FLAT_CHECKER_FIXTURES["flat_eval_v1"]),  # 0.58
        structured_response(FLAT_MAKER_FIXTURES["flat_v2"]),
        structured_response(FLAT_CHECKER_FIXTURES["flat_eval_v2"]),  # 0.58
        structured_response(FLAT_MAKER_FIXTURES["flat_v3"]),
        structured_response(FLAT_CHECKER_FIXTURES["flat_eval_v3"]),  # 0.58
    ]


# ── Test: converges ─────────────────────────────────────────────────────────


def test_converges() -> None:
    """Improves draft over 3 iterations until score >= 0.8."""
    model = ScriptedModel()
    model.set_response_sequence(_converge_sequence())

    with run_scope("evaluator-optimizer", "converges", max_model_calls=8, max_iterations=4) as ctx:
        result = run_evaluator_optimizer(ctx, model)

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output["status"] == "converged"
    assert result.output["iterations"] == 3
    assert result.output["scores"]["overall"] >= 0.8
    assert result.metrics["model_calls"] == 6.0
    assert result.metrics["tool_calls"] == 0.0


def test_converges_with_threshold_met() -> None:
    """Verify the final score exceeds the 0.8 threshold and a draft is present."""
    model = ScriptedModel()
    model.set_response_sequence(_converge_sequence())

    with run_scope("evaluator-optimizer", "converges_threshold", max_model_calls=8, max_iterations=4) as ctx:
        result = run_evaluator_optimizer(ctx, model)

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output["scores"]["overall"] >= 0.8
    assert result.output["draft"] is not None
    assert len(result.output["draft"]["sections"]) > 0


# ── Test: max iterations ────────────────────────────────────────────────────


def test_max_iterations_reached() -> None:
    """4 iterations hit, returns best draft with PARTIAL status."""
    model = ScriptedModel()
    model.set_response_sequence(_max_iter_sequence())

    with run_scope("evaluator-optimizer", "max_iter", max_model_calls=8, max_iterations=4) as ctx:
        result = run_evaluator_optimizer(ctx, model)

    assert result.status == ExecutionStatus.PARTIAL
    assert result.output["status"] == "max_iterations"
    assert result.output["iterations"] == 4
    assert result.output["draft"] is not None
    assert result.metrics["model_calls"] == 8.0
    assert result.metrics["iterations"] == 4.0


def test_max_iterations_all_scores_below_threshold() -> None:
    """All evaluation scores are below 0.8, confirming no convergence."""
    model = ScriptedModel()
    model.set_response_sequence(_max_iter_sequence())

    with run_scope("evaluator-optimizer", "max_iter_low", max_model_calls=8, max_iterations=4) as ctx:
        result = run_evaluator_optimizer(ctx, model)

    assert result.status == ExecutionStatus.PARTIAL
    scores = result.output["scores"]
    # scores is a dict of iter_N → RubricScores dict
    for key, sc in scores.items():
        assert isinstance(sc, dict), f"Expected dict, got {type(sc)} for {key}"
        assert sc["overall"] < 0.8, f"{key} has score {sc['overall']} >= 0.8"


# ── Test: no-progress detection ─────────────────────────────────────────────


def test_no_progress_detection() -> None:
    """Score flat for 2 iterations → stops early with PARTIAL status."""
    model = ScriptedModel()
    model.set_response_sequence(_no_progress_sequence())

    with run_scope("evaluator-optimizer", "no_progress", max_model_calls=8, max_iterations=4) as ctx:
        result = run_evaluator_optimizer(ctx, model)

    assert result.status == ExecutionStatus.PARTIAL
    assert result.output["status"] == "no_progress"
    # Should stop in 3 iterations (not 4)
    assert result.output["iterations"] == 3
    assert "No score improvement" in (result.failure_reason or "")
    assert result.metrics["model_calls"] < 8.0
    assert result.metrics["iterations"] == 3.0


# ── Test: evaluator failure fallback ────────────────────────────────────────


def test_evaluator_failure_fallback() -> None:
    """Evaluator returns error → uses last good draft with PARTIAL status.

    Uses fixture-key lookup (not response sequence) so the agent's own
    inject_checker_error_on parameter raises during the checker phase.
    """
    model = ScriptedModel()
    _register_all_fixtures(model)

    with run_scope("evaluator-optimizer", "eval_failure", max_model_calls=8, max_iterations=4) as ctx:
        result = run_evaluator_optimizer(
            ctx,
            model,
            maker_keys=["maker_v1", "maker_v2"],
            checker_keys=["checker_v1", "checker_v2"],
            inject_checker_error_on=4,  # Fail on the 4th ctx.model_call (2nd checker eval)
        )

    assert result.status == ExecutionStatus.PARTIAL
    assert result.output["status"] == "evaluator_failure_fallback"
    assert result.failure_reason is not None
    assert "failure" in result.failure_reason.lower() or "failed" in result.failure_reason.lower()
    assert result.output["draft"] is not None
    assert "scores" in result.output


# ── Test: independent vs same-model evaluator ───────────────────────────────


def test_independent_vs_same_evaluator() -> None:
    """Compare scores from different evaluator fixtures — they should differ."""
    model = ScriptedModel()
    _register_all_fixtures(model)

    draft = Proposal(
        title="Test Proposal",
        sections=["Summary: A test proposal.", "Impact: Minimal."],
        author="test",
    )

    with run_scope("evaluator-optimizer", "eval_compare", max_model_calls=8, max_iterations=4) as ctx:
        same_scores = evaluate_proposal(ctx, model, draft, "checker_v1")
        indep_scores = evaluate_proposal(ctx, model, draft, "checker_independent")

    assert same_scores is not None
    assert indep_scores is not None
    assert same_scores.overall != indep_scores.overall
    assert same_scores.clarity != indep_scores.clarity
    assert same_scores.feedback != indep_scores.feedback


# ── Test: rubric localized feedback ─────────────────────────────────────────


def test_rubric_localized_feedback() -> None:
    """Each section gets specific localized feedback from the evaluator."""
    model = ScriptedModel()
    _register_all_fixtures(model)

    draft = Proposal(
        title="Multi-Section Proposal",
        sections=[
            "Summary: Upgrade database to improve performance.",
            "Impact: 5-minute read-only window.",
            "Migration Plan: Steps 1-5 for cutover.",
            "Rollback Plan: DNS flip to revert.",
        ],
        author="platform-team",
    )

    with run_scope("evaluator-optimizer", "localized_feedback", max_model_calls=8, max_iterations=4) as ctx:
        scores = evaluate_proposal(ctx, model, draft, "checker_v3")

    assert scores is not None
    feedback = scores.feedback
    assert len(feedback) >= len(draft.sections)

    section_keywords = ["Summary", "Impact", "Migration", "Rollback"]
    for section_kw in section_keywords:
        matches = [fb for fb in feedback if section_kw.lower() in fb.lower()]
        assert len(matches) >= 1, f"No feedback referencing '{section_kw}' found in {feedback}"


# ── Test: state keys ────────────────────────────────────────────────────────


def test_state_keys_present() -> None:
    """State snapshot contains all required keys: draft, scores, iteration, best_draft, best_score."""
    model = ScriptedModel()
    model.set_response_sequence(_converge_sequence())

    with run_scope("evaluator-optimizer", "state_keys", max_model_calls=8, max_iterations=4) as ctx:
        result = run_evaluator_optimizer(ctx, model)

    state = result.state_snapshot
    assert "draft" in state
    assert "scores" in state
    assert "iteration" in state
    assert "best_draft" in state
    assert "best_score" in state


# ── Test: budget enforcement ────────────────────────────────────────────────


def test_budget_max_model_calls() -> None:
    """Enforce max_model_calls=8 — exactly 8 calls for 4 iterations."""
    model = ScriptedModel()
    model.set_response_sequence(_max_iter_sequence())

    with run_scope("evaluator-optimizer", "budget", max_model_calls=8, max_iterations=4) as ctx:
        result = run_evaluator_optimizer(ctx, model)

    assert result.metrics["model_calls"] == 8.0
    assert result.metrics["iterations"] == 4.0


# ── Test: audit events ─────────────────────────────────────────────────────


def test_audit_events_present() -> None:
    """Audit events are recorded for maker and checker phases."""
    model = ScriptedModel()
    model.set_response_sequence(_converge_sequence())

    with run_scope("evaluator-optimizer", "audit", max_model_calls=8, max_iterations=4) as ctx:
        result = run_evaluator_optimizer(ctx, model)

    assert len(result.audit_events) >= 6
    maker_calls = [e for e in result.audit_events if e.actor == "maker" and e.action == "model_call"]
    checker_calls = [e for e in result.audit_events if e.actor == "checker" and e.action == "model_call"]

    assert len(maker_calls) >= 1
    assert len(checker_calls) >= 1
