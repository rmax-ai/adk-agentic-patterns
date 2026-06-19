"""Pattern 07: Evaluator-Optimizer.

Scenario: Generate a technical change proposal and iteratively improve it
against a rubric.

The maker generates proposals; the checker evaluates them against a rubric
and returns typed scores with per-section feedback.  The loop iterates until:

1.  overall_score >= 0.8  (converged → SUCCEEDED)
2.  No score improvement for 2 consecutive iterations (→ PARTIAL)
3.  Max iterations (4) reached (→ PARTIAL with best draft)
4.  Evaluator raises an error (→ PARTIAL with last good draft)

Maker and checker are logically separate (different fixture sets).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from adk_patterns.contracts import ExecutionStatus, PatternRunResult
from adk_patterns.config import Config
from adk_patterns.models import ScriptedModel, structured_response
from adk_patterns.shared import RunContext, run_scope

# ── Contracts (inlined to avoid relative-import issues) ───────────────────


class Proposal(BaseModel):
    """A technical change proposal with structured sections."""

    title: str = Field(description="Short descriptive title of the proposal")
    sections: list[str] = Field(
        default_factory=list,
        description="Proposal sections (e.g., summary, impact, migration plan, rollback)",
    )
    author: str = Field(default="", description="Author of the proposal")


class RubricScores(BaseModel):
    """Rubric-based evaluation scores with localized per-section feedback."""

    clarity: float = Field(ge=0.0, le=1.0, description="Score for clarity of writing and structure")
    completeness: float = Field(ge=0.0, le=1.0, description="Score for completeness of coverage")
    feasibility: float = Field(ge=0.0, le=1.0, description="Score for feasibility and practicality")
    risk: float = Field(ge=0.0, le=1.0, description="Score for risk assessment quality")
    overall: float = Field(ge=0.0, le=1.0, description="Combined overall score")
    feedback: list[str] = Field(
        default_factory=list,
        description="Per-section localized feedback string for each evaluated section",
    )


# ── Fixtures (inlined to avoid relative-import issues) ────────────────────

MAKER_FIXTURES = {
    "maker_v1": {
        "title": "Migrate to PostgreSQL 16",
        "sections": [
            "Summary: Upgrade the production database from PostgreSQL 14 to 16 for improved performance and new features.",
            "Impact: All services that depend on the shared Postgres instance will experience ~5 min of read-only mode during migration.",
        ],
        "author": "infra-team",
    },
    "maker_v2": {
        "title": "Migrate to PostgreSQL 16 — v2",
        "sections": [
            "Summary: Upgrade from PostgreSQL 14 to 16. Expected 20% query performance improvement and native SQL/JSON support.",
            "Impact: Services experience read-only mode during the 5 min cutover. Write queues buffer during the window.",
            "Migration Plan: 1) Standby replica with PG16. 2) Replay WAL. 3) Validate. 4) Promote standby. 5) Redirect traffic.",
        ],
        "author": "infra-team",
    },
    "maker_v3": {
        "title": "Migrate to PostgreSQL 16 — v3",
        "sections": [
            "Summary: Database version upgrade delivering 20% faster queries, native JSON, and improved vacuum performance.",
            "Impact: 5 min read-only window. Write queues buffer automatically. Rollback is a DNS flip to the old primary.",
            "Migration Plan: Build PG16 replica \u2192 replay WAL \u2192 validate data \u2192 promote standby \u2192 switch DNS \u2192 decommission old primary.",
            "Rollback Plan: Flip DNS back to PG14 primary. Write queues drain naturally. Total RPO < 1 s.",
        ],
        "author": "infra-team",
    },
    "maker_v4": {
        "title": "Migrate to PostgreSQL 16 — v4",
        "sections": [
            "Summary: Zero-downtime upgrade from PG14 to PG16 with automated rollback and full observability.",
            "Impact: No user-facing downtime. Read replicas serve during cutover. Write buffers hold up to 60 s of traffic.",
            "Migration Plan: Deploy PG16 standby \u2192 sync via logical replication \u2192 validate checksums \u2192 promote \u2192 redirect via load balancer.",
            "Rollback Plan: Load balancer flips to old PG14 primary. Logical replication slot allows replay.",
            "Risk Assessment: Low \u2014 tested in staging three times. Monitoring dashboards validated for lag and replication status.",
        ],
        "author": "infra-team",
    },
}

CHECKER_FIXTURES = {
    "checker_v1": {
        "clarity": 0.55,
        "completeness": 0.45,
        "feasibility": 0.60,
        "risk": 0.50,
        "overall": 0.53,
        "feedback": [
            "Summary: clear but too brief \u2014 add expected performance metrics.",
            "Impact: missing migration plan and rollback strategy.",
        ],
    },
    "checker_v2": {
        "clarity": 0.65,
        "completeness": 0.60,
        "feasibility": 0.70,
        "risk": 0.55,
        "overall": 0.63,
        "feedback": [
            "Summary: improved, metrics help. Add concrete benchmark targets.",
            "Impact: migration plan present but lacks validation steps.",
            "Migration Plan: clear steps, add data validation and monitoring.",
        ],
    },
    "checker_v3": {
        "clarity": 0.85,
        "completeness": 0.80,
        "feasibility": 0.84,
        "risk": 0.78,
        "overall": 0.82,
        "feedback": [
            "Summary: well structured with clear metrics. Consider including cost estimate.",
            "Impact: comprehensive. Rollback plan present.",
            "Migration Plan: thorough with validation. Add monitoring checkpoints.",
            "Rollback Plan: good. Add RPO/RTO targets explicitly.",
        ],
    },
    "checker_v4": {
        "clarity": 0.90,
        "completeness": 0.88,
        "feasibility": 0.85,
        "risk": 0.82,
        "overall": 0.86,
        "feedback": [
            "Summary: excellent. All key metrics and stakeholders identified.",
            "Impact: zero-downtime claim supported with evidence from staging.",
            "Migration Plan: fully detailed with validation at every step.",
            "Rollback Plan: comprehensive with RPO/RTO targets.",
            "Risk Assessment: thorough. Staging evidence strengthens confidence.",
        ],
    },
}

FLAT_MAKER_FIXTURES = {
    "flat_v1": {
        "title": "Flat Proposal v1",
        "sections": [
            "Summary: Upgrade internal tooling to latest SDK version.",
            "Impact: Low \u2014 mostly internal tooling.",
        ],
        "author": "tools-team",
    },
    "flat_v2": {
        "title": "Flat Proposal v2",
        "sections": [
            "Summary: Upgrade internal tooling to latest SDK version (updated).",
            "Impact: Low \u2014 mostly internal tooling.",
            "Migration Plan: Simple package version bump.",
        ],
        "author": "tools-team",
    },
    "flat_v3": {
        "title": "Flat Proposal v3",
        "sections": [
            "Summary: Upgrade internal tooling SDK (final draft).",
            "Impact: Low.",
            "Migration Plan: Bump version, update imports, run tests.",
            "Rollback Plan: Revert package.json change.",
        ],
        "author": "tools-team",
    },
}

FLAT_CHECKER_FIXTURES = {
    "flat_eval_v1": {
        "clarity": 0.60,
        "completeness": 0.55,
        "feasibility": 0.65,
        "risk": 0.50,
        "overall": 0.58,
        "feedback": [
            "Summary: adequate but vague on scope.",
            "Impact: missing timeline and owner.",
        ],
    },
    "flat_eval_v2": {
        "clarity": 0.60,
        "completeness": 0.55,
        "feasibility": 0.65,
        "risk": 0.50,
        "overall": 0.58,
        "feedback": [
            "Summary: still vague. Add specific SDK version target.",
            "Impact: still missing timeline.",
        ],
    },
    "flat_eval_v3": {
        "clarity": 0.60,
        "completeness": 0.55,
        "feasibility": 0.65,
        "risk": 0.50,
        "overall": 0.58,
        "feedback": [
            "Summary: no improvement in clarity.",
            "Impact: timeline and owner still missing.",
            "Migration Plan: lacks testing strategy.",
        ],
    },
}

INDEPENDENT_CHECKER = {
    "checker_independent": {
        "clarity": 0.72,
        "completeness": 0.68,
        "feasibility": 0.70,
        "risk": 0.65,
        "overall": 0.69,
        "feedback": [
            "Summary: clear but cost-benefit analysis missing.",
            "Impact: timeline and owner identified; add monitoring plan.",
        ],
    },
}


# ── Default budgets ─────────────────────────────────────────────────────────

MAX_MODEL_CALLS = 8
MAX_ITERATIONS = 4
SCORE_THRESHOLD = 0.8
NO_PROGRESS_STREAK = 2  # consecutive iterations without score improvement


# ── Maker: generate or improve a proposal ──────────────────────────────────-


def generate_draft(
    ctx: RunContext,
    model: ScriptedModel,
    iteration: int,
    feedback: list[str] | None = None,
    fixture_key: str = "maker_v1",
) -> Proposal:
    """Call the maker to generate or improve a proposal.

    Args:
        ctx: Run context for audit tracking.
        model: Scripted model.
        iteration: Current iteration number (0-based).
        feedback: Optional per-section feedback from the previous evaluation.
        fixture_key: Fixture key for deterministic response.

    Returns:
        A Proposal object.
    """
    ctx.audit("maker", "model_call", resource="proposal", outcome="in_progress")

    system_instruction = (
        "You are a senior engineer writing a technical change proposal. "
        "Generate a structured proposal with clear sections."
    )
    if feedback:
        system_instruction += f" Improve the proposal based on this feedback: {feedback}"

    response = model.invoke(
        system_instruction=system_instruction,
        messages=[{"role": "user", "content": f"__FIXTURE__:{fixture_key} Iteration {iteration}"}],
    )

    ctx.record_model_call(tokens=response.usage.total_tokens)
    ctx.audit("maker", "model_response", outcome="success")

    if response.structured_output:
        return Proposal(**response.structured_output)

    # Fallback: fixture lookup
    fixture = MAKER_FIXTURES.get(fixture_key)
    if fixture is None:
        ctx.mark_failed(f"No maker fixture for key: {fixture_key}")
        raise ValueError(f"No maker fixture for key: {fixture_key}")
    return Proposal(**fixture)


# ── Checker: evaluate proposal against rubric ──────────────────────────────


def evaluate_proposal(
    ctx: RunContext,
    model: ScriptedModel,
    draft: Proposal,
    fixture_key: str = "checker_v1",
) -> RubricScores | None:
    """Evaluate a proposal against the rubric and return typed scores.

    Returns None if the evaluator fails (to trigger fallback logic).
    """
    ctx.audit("checker", "model_call", resource="rubric", outcome="in_progress")

    system_instruction = (
        "You are a technical reviewer. Evaluate the proposal on four criteria: "
        "clarity, completeness, feasibility, and risk assessment. "
        "Return per-section feedback for each section."
    )

    response = model.invoke(
        system_instruction=system_instruction,
        messages=[
            {
                "role": "user",
                "content": (
                    f"__FIXTURE__:{fixture_key} Evaluate this proposal:\n"
                    f"Title: {draft.title}\n"
                    f"Sections: {draft.sections}"
                ),
            }
        ],
    )

    ctx.record_model_call(tokens=response.usage.total_tokens)
    ctx.audit("checker", "model_response", outcome="success")

    if response.structured_output:
        return RubricScores(**response.structured_output)

    fixture = CHECKER_FIXTURES.get(fixture_key) or INDEPENDENT_CHECKER.get(fixture_key)
    if fixture is None:
        ctx.audit("checker", "fixture_not_found", outcome="failure", metadata={"key": fixture_key})
        return None
    return RubricScores(**fixture)


# ── Core evaluator-optimizer loop ───────────────────────────────────────────


def run_evaluator_optimizer(
    ctx: RunContext,
    model: ScriptedModel,
    maker_keys: list[str] | None = None,
    checker_keys: list[str] | None = None,
    inject_checker_error_on: int | None = None,
) -> PatternRunResult:
    """Run the evaluator-optimizer loop with deterministic fixtures.

    Args:
        ctx: Run context for audit, budget, and state tracking.
        model: Scripted model with registered fixtures.
        maker_keys: Ordered list of maker fixture keys for each iteration.
        checker_keys: Ordered list of checker fixture keys for each iteration.
        inject_checker_error_on: If set, the Nth checker call raises an error.

    Returns:
        PatternRunResult with the final output and state.
    """
    mk = maker_keys or ["maker_v1", "maker_v2", "maker_v3", "maker_v4"]
    ck = checker_keys or ["checker_v1", "checker_v2", "checker_v3", "checker_v4"]

    state: dict[str, Any] = {
        "draft": None,
        "scores": {},
        "iteration": 0,
        "best_draft": None,
        "best_score": 0.0,
    }

    previous_overall: float | None = None
    no_progress_count = 0

    while state["iteration"] < MAX_ITERATIONS:
        # ── Budget check ──
        budget_status = ctx.check_budget()
        if budget_status is not None:
            ctx.status = budget_status
            break

        iteration = state["iteration"]
        maker_key = mk[iteration] if iteration < len(mk) else mk[-1]
        checker_key = ck[iteration] if iteration < len(ck) else ck[-1]

        ctx.record_iteration()

        # ── 1. Maker: generate / improve draft ──
        feedback: list[str] = []
        if state["scores"]:
            # Pull feedback from the last successful evaluation
            last_scores = list(state["scores"].values())[-1]
            if isinstance(last_scores, dict) and "feedback" in last_scores:
                feedback = last_scores["feedback"]

        try:
            proposal = generate_draft(ctx, model, iteration, feedback, maker_key)
        except Exception as e:
            ctx.mark_failed(f"Maker failed at iteration {iteration}: {e}")
            break

        state["draft"] = proposal.model_dump()
        ctx.snapshot_state(dict(state))

        # ── 2. Checker: evaluate draft ──
        try:
            if inject_checker_error_on is not None and ctx.model_calls >= inject_checker_error_on:
                raise RuntimeError(f"Simulated evaluator failure (call #{inject_checker_error_on})")

            scores = evaluate_proposal(ctx, model, proposal, checker_key)
        except Exception as e:
            # ── Evaluator failure fallback ──
            ctx.audit(
                "checker",
                "model_response",
                outcome="failure",
                metadata={"error": str(e), "iteration": iteration},
            )
            if state["best_draft"] is not None:
                ctx.status = ExecutionStatus.PARTIAL
                ctx.failure_reason = f"Evaluator failed at iteration {iteration}: {e}"
                ctx.output = {
                    "draft": state["best_draft"],
                    "scores": list(state["scores"].values())[-1] if state["scores"] else {},
                    "iterations": iteration,
                    "status": "evaluator_failure_fallback",
                }
                ctx.snapshot_state(dict(state))
                return ctx.to_result()
            ctx.mark_failed(f"Evaluator failed with no fallback draft: {e}")
            break

        if scores is None:
            # Fixture not found — same as evaluator failure
            ctx.audit("checker", "fixture_not_found", outcome="failure")
            if state["best_draft"] is not None:
                ctx.status = ExecutionStatus.PARTIAL
                ctx.failure_reason = f"Checker fixture not found for key: {checker_key}"
                ctx.output = {
                    "draft": state["best_draft"],
                    "scores": list(state["scores"].values())[-1] if state["scores"] else {},
                    "iterations": iteration,
                    "status": "evaluator_failure_fallback",
                }
                ctx.snapshot_state(dict(state))
                return ctx.to_result()
            ctx.mark_failed(f"Checker fixture not found: {checker_key}")
            break

        # Record scores
        score_dict = scores.model_dump()
        state["scores"][f"iter_{iteration}"] = score_dict

        # Track best
        if scores.overall > state["best_score"]:
            state["best_score"] = scores.overall
            state["best_draft"] = proposal.model_dump()

        ctx.snapshot_state(dict(state))

        # ── Check threshold ──
        if scores.overall >= SCORE_THRESHOLD:
            ctx.audit(
                "checker",
                "threshold_met",
                outcome="success",
                metadata={"score": scores.overall, "iteration": iteration},
            )
            ctx.output = {
                "draft": proposal.model_dump(),
                "scores": score_dict,
                "iterations": iteration + 1,
                "status": "converged",
            }
            ctx.snapshot_state(dict(state))
            return ctx.to_result()

        # ── No-progress detection ──
        if previous_overall is not None:
            if scores.overall <= previous_overall:
                no_progress_count += 1
            else:
                no_progress_count = 0

            if no_progress_count >= NO_PROGRESS_STREAK:
                ctx.audit(
                    "checker",
                    "no_progress",
                    outcome="partial",
                    metadata={
                        "score": scores.overall,
                        "previous": previous_overall,
                        "streak": no_progress_count,
                    },
                )
                ctx.status = ExecutionStatus.PARTIAL
                ctx.failure_reason = (
                    f"No score improvement for {NO_PROGRESS_STREAK} consecutive iterations. "
                    f"Best score: {state['best_score']:.2f}"
                )
                ctx.output = {
                    "draft": state["best_draft"],
                    "scores": score_dict,
                    "iterations": iteration + 1,
                    "status": "no_progress",
                }
                ctx.snapshot_state(dict(state))
                return ctx.to_result()

        previous_overall = scores.overall
        state["iteration"] += 1

    # ── Max iterations reached ──
    ctx.audit(
        "loop",
        "max_iterations_reached",
        outcome="partial",
        metadata={
            "iterations": state["iteration"],
            "best_score": state["best_score"],
        },
    )
    ctx.status = ExecutionStatus.PARTIAL
    ctx.failure_reason = f"Max iterations ({MAX_ITERATIONS}) reached. Best score: {state['best_score']:.2f}"
    ctx.output = {
        "draft": state["best_draft"],
        "scores": state["scores"],
        "iterations": state["iteration"],
        "status": "max_iterations",
    }
    ctx.snapshot_state(dict(state))
    return ctx.to_result()


# ── Fixture registration ────────────────────────────────────────────────────


def _register_maker_fixtures(model: ScriptedModel) -> None:
    """Register maker fixtures so the model can look them up by key."""
    for key, value in MAKER_FIXTURES.items():
        model.register_fixture(key, structured_response(value))


def _register_checker_fixtures(model: ScriptedModel) -> None:
    """Register checker fixtures so the model can look them up by key."""
    for key, value in CHECKER_FIXTURES.items():
        model.register_fixture(key, structured_response(value))
    for key, value in INDEPENDENT_CHECKER.items():
        model.register_fixture(key, structured_response(value))


def _register_flat_fixtures(model: ScriptedModel) -> None:
    """Register flat-score fixtures for no-progress tests."""
    for key, value in FLAT_MAKER_FIXTURES.items():
        model.register_fixture(key, structured_response(value))
    for key, value in FLAT_CHECKER_FIXTURES.items():
        model.register_fixture(key, structured_response(value))


def _register_all_fixtures(model: ScriptedModel) -> None:
    """Register all fixtures on the model."""
    _register_maker_fixtures(model)
    _register_checker_fixtures(model)
    _register_flat_fixtures(model)


# ── Public entry points ─────────────────────────────────────────────────────


def run(
    config: Config | None = None,
    scenario: str = "default",
    maker_keys: list[str] | None = None,
    checker_keys: list[str] | None = None,
    inject_checker_error_on: int | None = None,
) -> PatternRunResult:
    """Entry point for CLI and tests.

    Args:
        config: Application configuration (uses defaults if None).
        scenario: Scenario name for audit tracking.
        maker_keys: Ordered maker fixture keys (default: v1\u2192v2\u2192v3\u2192v4).
        checker_keys: Ordered checker fixture keys (default: v1\u2192v2\u2192v3\u2192v4).
        inject_checker_error_on: If set, checker raises on this model call index.

    Returns:
        PatternRunResult with draft, scores, and metrics.
    """
    model = ScriptedModel()
    _register_all_fixtures(model)

    with run_scope(
        "evaluator-optimizer",
        scenario,
        max_model_calls=MAX_MODEL_CALLS,
        max_iterations=MAX_ITERATIONS,
    ) as ctx:
        result = run_evaluator_optimizer(
            ctx,
            model,
            maker_keys=maker_keys,
            checker_keys=checker_keys,
            inject_checker_error_on=inject_checker_error_on,
        )
        return result

    # Fallback (should not reach here)
    return ctx.to_result()


def main(config: Config | None = None, scenario: str = "default") -> PatternRunResult:
    """Standard entry point called by CLI."""
    return run(config=config, scenario=scenario)
