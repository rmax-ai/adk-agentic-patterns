"""Pattern 09: Sequential Specialists.

Scenario: Process an insurance claim through four sequential specialist stages:
  Stage 1 — Extraction: extract structured claim data from raw text
  Stage 2 — Eligibility: determine if the claim is covered
  Stage 3 — Fraud Screening: detect potential fraud indicators
  Stage 4 — Explanation: generate a human-readable claim decision

KEY CONCEPT — Sequential Specialists vs. Arbitrary Multi-Agent Role Play:
  Each specialist has exactly one typed responsibility with a Pydantic contract.
  Output from stage N is the ONLY input to stage N+1 — no shared memory,
  no message passing, no "personalities." This is a deterministic pipeline
  with typed data contracts between stages, enforced by schema validation.
  Arbitrary role play lets agents chat freely, share a chat history, override
  each other's decisions, or drift from their assigned task. Sequential
  Specialists cannot drift — the contracts prevent it.

STATE KEYS (each stage owns exactly one, written via snapshot_state):
  extracted_claim   ← Stage 1 (Extraction)
  eligibility_result ← Stage 2 (Eligibility)
  fraud_result       ← Stage 3 (Fraud Screening)
  explanation        ← Stage 4 (Explanation)

BUDGET: max_model_calls=4, max_iterations=0
"""

from __future__ import annotations

import sys
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from adk_patterns.contracts import PatternRunResult
from adk_patterns.config import Config
from adk_patterns.models import ScriptedModel, structured_response
from adk_patterns.shared import RunContext, run_scope

# Add this directory to sys.path so we can import from sibling modules
_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))

from contracts import ClaimExplanation, EligibilityVerdict, ExtractedClaim, FraudScreeningResult
from fixtures import register_all
from mocks import get_claim_text, get_scenario_fixture, is_valid_scenario


# ── Stage functions (specialist agents) ─────────────────────────────────────


def stage1_extract_claim(
    ctx: RunContext,
    model: ScriptedModel,
    scenario: str,
    claim_text: str,
) -> ExtractedClaim | None:
    """Stage 1 — Extraction Specialist: parse raw text into structured claim data.

    Returns validated ExtractedClaim or None (and marks ctx as failed).
    """
    ctx.audit("extraction", "model_call", resource="claim_extraction")
    ctx.record_model_call(tokens=120)

    fixture_key = get_scenario_fixture(scenario, "stage1")
    if fixture_key is None:
        fixture_key = "stage1_valid_auto"

    response = model.invoke(
        system_instruction=(
            "You are a claims extraction specialist. Extract structured claim "
            "data from the raw submission text. Return all fields precisely."
        ),
        messages=[{"role": "user", "content": f"__FIXTURE__:{fixture_key} {claim_text}"}],
    )

    ctx.audit("extraction", "model_response", outcome="success")

    data = response.structured_output
    if data is None:
        ctx.audit("extraction", "validation_failed", outcome="failure", metadata={"reason": "no_structured_output"})
        ctx.mark_failed("Stage 1 (Extraction): model returned no structured output")
        return None

    try:
        claim = ExtractedClaim(**data)
    except ValidationError as e:
        ctx.audit("extraction", "validation_failed", outcome="failure", metadata={"errors": str(e)})
        ctx.mark_failed(f"Stage 1 (Extraction): schema validation failed — {e.errors()}")
        return None

    ctx.snapshot_state({"extracted_claim": claim.model_dump()})
    return claim


def stage2_check_eligibility(
    ctx: RunContext,
    model: ScriptedModel,
    claim: ExtractedClaim,
    scenario: str,
) -> EligibilityVerdict | None:
    """Stage 2 — Eligibility Specialist: determine if the claim is covered.

    Only runs if Stage 1 succeeded. Returns validated EligibilityVerdict or None.
    """
    ctx.audit("eligibility", "model_call", resource="claim_eligibility")
    ctx.record_model_call(tokens=120)

    fixture_key = get_scenario_fixture(scenario, "stage2")
    if fixture_key is None:
        fixture_key = "stage2_approved_auto"

    response = model.invoke(
        system_instruction=(
            "You are an eligibility specialist. Based on the extracted claim details, "
            "determine whether this claim is eligible for coverage under the policy. "
            "Return the eligibility verdict with the eligible amount and reason."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"__FIXTURE__:{fixture_key} "
                    f"Claim: {claim.model_dump_json()}"
                ),
            },
        ],
    )

    ctx.audit("eligibility", "model_response", outcome="success")

    data = response.structured_output
    if data is None:
        ctx.audit("eligibility", "validation_failed", outcome="failure", metadata={"reason": "no_structured_output"})
        ctx.mark_failed("Stage 2 (Eligibility): model returned no structured output")
        return None

    try:
        verdict = EligibilityVerdict(**data)
    except ValidationError as e:
        ctx.audit("eligibility", "validation_failed", outcome="failure", metadata={"errors": str(e)})
        ctx.mark_failed(f"Stage 2 (Eligibility): schema validation failed — {e.errors()}")
        return None

    ctx.snapshot_state({"eligibility_result": verdict.model_dump()})
    return verdict


def stage3_screen_fraud(
    ctx: RunContext,
    model: ScriptedModel,
    claim: ExtractedClaim,
    verdict: EligibilityVerdict,
    scenario: str,
) -> FraudScreeningResult | None:
    """Stage 3 — Fraud Screening Specialist: detect fraud indicators.

    Only runs if Stages 1 and 2 succeeded AND the claim is eligible.
    Returns validated FraudScreeningResult or None.
    """
    ctx.audit("fraud_screening", "model_call", resource="fraud_screening")
    ctx.record_model_call(tokens=120)

    fixture_key = get_scenario_fixture(scenario, "stage3")
    if fixture_key is None:
        fixture_key = "stage3_clean_auto"

    response = model.invoke(
        system_instruction=(
            "You are a fraud screening specialist. Analyze the claim details "
            "and eligibility verdict for fraud indicators. Return the screening "
            "result with risk score and any suspicious flags."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"__FIXTURE__:{fixture_key} "
                    f"Claim: {claim.model_dump_json()} "
                    f"Eligibility: {verdict.model_dump_json()}"
                ),
            },
        ],
    )

    ctx.audit("fraud_screening", "model_response", outcome="success")

    data = response.structured_output
    if data is None:
        ctx.audit("fraud_screening", "validation_failed", outcome="failure", metadata={"reason": "no_structured_output"})
        ctx.mark_failed("Stage 3 (Fraud Screening): model returned no structured output")
        return None

    try:
        fraud_result = FraudScreeningResult(**data)
    except ValidationError as e:
        ctx.audit("fraud_screening", "validation_failed", outcome="failure", metadata={"errors": str(e)})
        ctx.mark_failed(f"Stage 3 (Fraud Screening): schema validation failed — {e.errors()}")
        return None

    ctx.snapshot_state({"fraud_result": fraud_result.model_dump()})
    return fraud_result


def stage4_generate_explanation(
    ctx: RunContext,
    model: ScriptedModel,
    claim: ExtractedClaim,
    verdict: EligibilityVerdict,
    fraud_result: FraudScreeningResult,
    scenario: str,
) -> ClaimExplanation | None:
    """Stage 4 — Explanation Specialist: generate a human-readable claim explanation.

    Only runs if all previous stages succeeded and fraud screening is clean.
    Returns validated ClaimExplanation or None.
    """
    ctx.audit("explanation", "model_call", resource="claim_explanation")
    ctx.record_model_call(tokens=120)

    fixture_key = get_scenario_fixture(scenario, "stage4")
    if fixture_key is None:
        fixture_key = "stage4_approved_auto"

    response = model.invoke(
        system_instruction=(
            "You are a claims explanation specialist. Generate a clear, "
            "human-readable explanation of the claim decision based on the "
            "extracted claim, eligibility verdict, and fraud screening results. "
            "Include coverage details, payment amount, and next steps."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"__FIXTURE__:{fixture_key} "
                    f"Claim: {claim.model_dump_json()} "
                    f"Eligibility: {verdict.model_dump_json()} "
                    f"Fraud Screening: {fraud_result.model_dump_json()}"
                ),
            },
        ],
    )

    ctx.audit("explanation", "model_response", outcome="success")

    data = response.structured_output
    if data is None:
        ctx.audit("explanation", "validation_failed", outcome="failure", metadata={"reason": "no_structured_output"})
        ctx.mark_failed("Stage 4 (Explanation): model returned no structured output")
        return None

    try:
        explanation = ClaimExplanation(**data)
    except ValidationError as e:
        ctx.audit("explanation", "validation_failed", outcome="failure", metadata={"errors": str(e)})
        ctx.mark_failed(f"Stage 4 (Explanation): schema validation failed — {e.errors()}")
        return None

    ctx.snapshot_state({"explanation": explanation.model_dump()})
    return explanation


# ── Run entry point ─────────────────────────────────────────────────────────


def run(config: Config | None = None, scenario: str = "default") -> PatternRunResult:
    """Execute the sequential specialists pipeline: extraction → eligibility → fraud → explanation.

    Args:
        config: Application configuration (uses defaults if None).
        scenario: Test scenario name (valid_auto, valid_property, ineligible, fraud_suspicious).

    Returns:
        PatternRunResult with the final output or failure information.
    """
    model = ScriptedModel()
    register_all(model)

    scenario_key = scenario if is_valid_scenario(scenario) else "valid_auto"
    claim_text = get_claim_text(scenario_key)

    with run_scope(
        "sequential-specialists",
        scenario,
        max_model_calls=4,
        max_tool_calls=0,
        max_iterations=0,
    ) as ctx:
        # ── Stage 1: Extraction ──────────────────────────────────────────
        claim = stage1_extract_claim(ctx, model, scenario_key, claim_text)
        if claim is None:
            ctx.output = {"extracted_claim": "validation_failed"}
            return ctx.to_result()

        # ── Stage 2: Eligibility ─────────────────────────────────────────
        verdict = stage2_check_eligibility(ctx, model, claim, scenario_key)
        if verdict is None:
            ctx.output = {
                "extracted_claim": claim.model_dump(),
                "eligibility_result": "validation_failed",
            }
            return ctx.to_result()

        # ── Stop early if ineligible ────────────────────────────────────
        if not verdict.is_eligible:
            ctx.output = {
                "extracted_claim": claim.model_dump(),
                "eligibility_result": verdict.model_dump(),
            }
            return ctx.to_result()

        # ── Stage 3: Fraud Screening ────────────────────────────────────
        fraud_result = stage3_screen_fraud(ctx, model, claim, verdict, scenario_key)
        if fraud_result is None:
            ctx.output = {
                "extracted_claim": claim.model_dump(),
                "eligibility_result": verdict.model_dump(),
                "fraud_result": "validation_failed",
            }
            return ctx.to_result()

        # ── Stop early if fraud detected ───────────────────────────────
        if fraud_result.is_suspicious:
            ctx.output = {
                "extracted_claim": claim.model_dump(),
                "eligibility_result": verdict.model_dump(),
                "fraud_result": fraud_result.model_dump(),
            }
            return ctx.to_result()

        # ── Stage 4: Explanation ─────────────────────────────────────────
        explanation = stage4_generate_explanation(
            ctx, model, claim, verdict, fraud_result, scenario_key
        )
        if explanation is None:
            ctx.output = {
                "extracted_claim": claim.model_dump(),
                "eligibility_result": verdict.model_dump(),
                "fraud_result": fraud_result.model_dump(),
                "explanation": "validation_failed",
            }
            return ctx.to_result()

        # ── Success: aggregate all outputs ──────────────────────────────
        ctx.output = {
            "extracted_claim": claim.model_dump(),
            "eligibility_result": verdict.model_dump(),
            "fraud_result": fraud_result.model_dump(),
            "explanation": explanation.model_dump(),
        }
        ctx.snapshot_state(ctx.output)

    return ctx.to_result()


# ── CLI entry point ─────────────────────────────────────────────────────────


def main(config: Config | None = None, scenario: str = "default") -> PatternRunResult:
    """Standard entry point called by CLI."""
    return run(config=config, scenario=scenario)
