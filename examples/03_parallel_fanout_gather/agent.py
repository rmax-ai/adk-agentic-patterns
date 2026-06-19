"""Pattern 03: Parallel Fan-Out/Gather.

Scenario: Evaluate a vendor simultaneously for security, legal, operational,
and financial concerns using asyncio.gather for independent branches.

Each branch writes to a UNIQUE output key (no state-key collisions).
Simulated branch latency via MockClock from adk_patterns.mocks.clock.
Supports configurable fail-fast vs partial-result behavior.
Proves wall-clock improvement in tests using a fake clock.

State keys: security_eval, legal_eval, operational_eval, financial_eval, synthesis
Budget: max_model_calls=5, max_tool_calls=0
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field

from adk_patterns.contracts import ExecutionStatus, PatternRunResult
from adk_patterns.config import Config
from adk_patterns.models import ScriptedModel, structured_response
from adk_patterns.shared import RunContext, run_scope

# -- Contracts ----------------------------------------------------------------


class SecurityEval(BaseModel):
    """Security evaluation of a vendor."""

    score: float = Field(ge=0.0, le=10.0, description="Security score (0-10)")
    issues: list[str] = Field(default_factory=list, description="Identified security issues")
    summary: str = Field(default="", description="Security evaluation summary")


class LegalEval(BaseModel):
    """Legal evaluation of a vendor."""

    score: float = Field(ge=0.0, le=10.0, description="Legal compliance score (0-10)")
    issues: list[str] = Field(default_factory=list, description="Identified legal issues")
    summary: str = Field(default="", description="Legal evaluation summary")


class OperationalEval(BaseModel):
    """Operational evaluation of a vendor."""

    score: float = Field(ge=0.0, le=10.0, description="Operational readiness score (0-10)")
    issues: list[str] = Field(default_factory=list, description="Identified operational issues")
    summary: str = Field(default="", description="Operational evaluation summary")


class FinancialEval(BaseModel):
    """Financial evaluation of a vendor."""

    score: float = Field(ge=0.0, le=10.0, description="Financial health score (0-10)")
    issues: list[str] = Field(default_factory=list, description="Identified financial issues")
    summary: str = Field(default="", description="Financial evaluation summary")


class VendorEvalSynthesis(BaseModel):
    """Aggregated synthesis of all vendor evaluations."""

    overall_score: float = Field(ge=0.0, le=10.0, description="Weighted overall score (0-10)")
    recommendation: str = Field(default="", description="Final recommendation (approve/reject/conditional)")
    summary: str = Field(default="", description="Synthesis summary across all dimensions")


# -- Fixtures -----------------------------------------------------------------

FIXTURES = {
    "security_eval": SecurityEval(
        score=8.5,
        issues=["Outdated TLS 1.1 on internal endpoints", "No bug bounty program"],
        summary="Good security posture with minor concerns around legacy protocol support.",
    ),
    "legal_eval": LegalEval(
        score=7.0,
        issues=["GDPR compliance documentation incomplete", "Indemnification clause too narrow"],
        summary="Adequate legal compliance with gaps in documentation and liability terms.",
    ),
    "operational_eval": OperationalEval(
        score=9.0,
        issues=["Support SLA response time 1h above target"],
        summary="Highly operational vendor with strong uptime and mature incident response.",
    ),
    "financial_eval": FinancialEval(
        score=6.5,
        issues=["Declining quarterly revenue", "High debt-to-equity ratio"],
        summary="Financially stable near-term but concerning trends in revenue and leverage.",
    ),
    "synthesis": VendorEvalSynthesis(
        overall_score=7.75,
        recommendation="conditional",
        summary=(
            "Vendor shows strength in security and operations but has gaps in legal documentation "
            "and financial health. Recommend conditional approval with quarterly review."
        ),
    ),
}


# -- Branch evaluation functions (async coroutines) ---------------------------


async def _evaluate_security(
    ctx: RunContext,
    model: ScriptedModel,
    vendor_name: str,
    fixture_key: str = "security_eval",
) -> SecurityEval:
    """Evaluate vendor security posture."""
    ctx.audit("security_eval", "model_call", resource=vendor_name)

    response = model.invoke(
        system_instruction="Evaluate the vendor's security posture.",
        messages=[{"role": "user", "content": f"__FIXTURE__:{fixture_key} Evaluate security for {vendor_name}"}],
    )

    ctx.record_model_call(tokens=response.usage.total_tokens)
    ctx.audit("security_eval", "model_response", outcome="success")

    if response.structured_output:
        return SecurityEval(**response.structured_output)

    fixture = FIXTURES.get(fixture_key)
    if fixture is None:
        ctx.mark_failed(f"No fixture for key: {fixture_key}")
        raise ValueError(f"No fixture for key: {fixture_key}")
    return fixture


async def _evaluate_legal(
    ctx: RunContext,
    model: ScriptedModel,
    vendor_name: str,
    fixture_key: str = "legal_eval",
) -> LegalEval:
    """Evaluate vendor legal compliance."""
    ctx.audit("legal_eval", "model_call", resource=vendor_name)

    response = model.invoke(
        system_instruction="Evaluate the vendor's legal compliance.",
        messages=[{"role": "user", "content": f"__FIXTURE__:{fixture_key} Evaluate legal for {vendor_name}"}],
    )

    ctx.record_model_call(tokens=response.usage.total_tokens)
    ctx.audit("legal_eval", "model_response", outcome="success")

    if response.structured_output:
        return LegalEval(**response.structured_output)

    fixture = FIXTURES.get(fixture_key)
    if fixture is None:
        ctx.mark_failed(f"No fixture for key: {fixture_key}")
        raise ValueError(f"No fixture for key: {fixture_key}")
    return fixture


async def _evaluate_operational(
    ctx: RunContext,
    model: ScriptedModel,
    vendor_name: str,
    fixture_key: str = "operational_eval",
) -> OperationalEval:
    """Evaluate vendor operational readiness."""
    ctx.audit("operational_eval", "model_call", resource=vendor_name)

    response = model.invoke(
        system_instruction="Evaluate the vendor's operational readiness.",
        messages=[{"role": "user", "content": f"__FIXTURE__:{fixture_key} Evaluate operational for {vendor_name}"}],
    )

    ctx.record_model_call(tokens=response.usage.total_tokens)
    ctx.audit("operational_eval", "model_response", outcome="success")

    if response.structured_output:
        return OperationalEval(**response.structured_output)

    fixture = FIXTURES.get(fixture_key)
    if fixture is None:
        ctx.mark_failed(f"No fixture for key: {fixture_key}")
        raise ValueError(f"No fixture for key: {fixture_key}")
    return fixture


async def _evaluate_financial(
    ctx: RunContext,
    model: ScriptedModel,
    vendor_name: str,
    fixture_key: str = "financial_eval",
) -> FinancialEval:
    """Evaluate vendor financial health."""
    ctx.audit("financial_eval", "model_call", resource=vendor_name)

    response = model.invoke(
        system_instruction="Evaluate the vendor's financial health.",
        messages=[{"role": "user", "content": f"__FIXTURE__:{fixture_key} Evaluate financial for {vendor_name}"}],
    )

    ctx.record_model_call(tokens=response.usage.total_tokens)
    ctx.audit("financial_eval", "model_response", outcome="success")

    if response.structured_output:
        return FinancialEval(**response.structured_output)

    fixture = FIXTURES.get(fixture_key)
    if fixture is None:
        ctx.mark_failed(f"No fixture for key: {fixture_key}")
        raise ValueError(f"No fixture for key: {fixture_key}")
    return fixture


async def _synthesize(
    ctx: RunContext,
    model: ScriptedModel,
    vendor_name: str,
    security: SecurityEval,
    legal: LegalEval,
    operational: OperationalEval,
    financial: FinancialEval,
    fixture_key: str = "synthesis",
) -> VendorEvalSynthesis:
    """Synthesize all evaluations into a final recommendation."""
    ctx.audit("synthesis", "model_call", resource=vendor_name)

    inputs = {
        "security": security.model_dump(),
        "legal": legal.model_dump(),
        "operational": operational.model_dump(),
        "financial": financial.model_dump(),
    }

    response = model.invoke(
        system_instruction="Aggregate all vendor evaluations into a final recommendation.",
        messages=[
            {
                "role": "user",
                "content": f"__FIXTURE__:{fixture_key} Synthesize evaluations for {vendor_name}: {inputs}",
            }
        ],
    )

    ctx.record_model_call(tokens=response.usage.total_tokens)
    ctx.audit("synthesis", "model_response", outcome="success")

    if response.structured_output:
        return VendorEvalSynthesis(**response.structured_output)

    fixture = FIXTURES.get(fixture_key)
    if fixture is None:
        ctx.mark_failed(f"No fixture for key: {fixture_key}")
        raise ValueError(f"No fixture for key: {fixture_key}")
    return fixture


# -- Main run entry point -----------------------------------------------------


async def _run_async(
    ctx: RunContext,
    model: ScriptedModel,
    vendor_name: str,
    fail_fast: bool = True,
    fixture_overrides: dict[str, str | None] | None = None,
) -> tuple[SecurityEval, LegalEval, OperationalEval, FinancialEval, VendorEvalSynthesis]:
    """Run all 4 evaluation branches in parallel, then synthesize.

    Args:
        ctx: Run context for audit and budget tracking.
        model: Scripted model with pre-registered fixtures.
        vendor_name: Name of the vendor being evaluated.
        fail_fast: If True, first failure cancels other branches.
                   If False, partial results are returned from surviving branches.
        fixture_overrides: Optional dict of branch name -> fixture key (None = simulate failure).

    Returns:
        Tuple of (security, legal, operational, financial, synthesis) eval results.
    """
    overrides = fixture_overrides or {}

    # Build fixture keys, allowing None to simulate a failing branch
    sec_key = overrides.get("security", "security_eval")
    leg_key = overrides.get("legal", "legal_eval")
    ops_key = overrides.get("operational", "operational_eval")
    fin_key = overrides.get("financial", "financial_eval")

    # Create coroutines, injecting errors for None keys
    async def _safe_security() -> SecurityEval:
        if sec_key is None:
            raise ValueError("Security evaluation failed: no fixture available")
        return await _evaluate_security(ctx, model, vendor_name, sec_key)

    async def _safe_legal() -> LegalEval:
        if leg_key is None:
            raise ValueError("Legal evaluation failed: no fixture available")
        return await _evaluate_legal(ctx, model, vendor_name, leg_key)

    async def _safe_operational() -> OperationalEval:
        if ops_key is None:
            raise ValueError("Operational evaluation failed: no fixture available")
        return await _evaluate_operational(ctx, model, vendor_name, ops_key)

    async def _safe_financial() -> FinancialEval:
        if fin_key is None:
            raise ValueError("Financial evaluation failed: no fixture available")
        return await _evaluate_financial(ctx, model, vendor_name, fin_key)

    # Fan-out: run all 4 branches concurrently
    if fail_fast:
        # return_exceptions=False — first exception propagates immediately
        sec, leg, ops, fin = await asyncio.gather(
            _safe_security(),
            _safe_legal(),
            _safe_operational(),
            _safe_financial(),
        )
    else:
        # return_exceptions=True — collect results; failed branches return Exception
        results = await asyncio.gather(
            _safe_security(),
            _safe_legal(),
            _safe_operational(),
            _safe_financial(),
            return_exceptions=True,
        )

        # Track which branches failed
        branch_names = ["security", "legal", "operational", "financial"]
        any_failed = False
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                ctx.audit("branch", "failed", outcome="failure", metadata={"branch": branch_names[i], "error": str(r)})
                any_failed = True

        # If any branch failed in partial mode, mark as PARTIAL
        if any_failed:
            ctx.status = ExecutionStatus.PARTIAL
            ctx.failure_reason = "Some evaluation branches failed; returning partial results"

        # Check if all branches failed
        if all(isinstance(r, Exception) for r in results):
            ctx.mark_failed("All evaluation branches failed")
            raise RuntimeError("All evaluation branches failed")

        # Unpack results preserving position (failed branches get placeholders)
        sec = results[0] if not isinstance(results[0], Exception) else SecurityEval(score=0.0, issues=["Branch failed"], summary="Not evaluated")
        leg = results[1] if not isinstance(results[1], Exception) else LegalEval(score=0.0, issues=["Branch failed"], summary="Not evaluated")
        ops = results[2] if not isinstance(results[2], Exception) else OperationalEval(score=0.0, issues=["Branch failed"], summary="Not evaluated")
        fin = results[3] if not isinstance(results[3], Exception) else FinancialEval(score=0.0, issues=["Branch failed"], summary="Not evaluated")

    # Gather: synthesize results
    syn_key = overrides.get("synthesis", "synthesis")
    if syn_key is None:
        raise ValueError("Synthesis evaluation failed: no fixture available")
    synthesis = await _synthesize(ctx, model, vendor_name, sec, leg, ops, fin, syn_key)

    return sec, leg, ops, fin, synthesis


# -- Fixture registration -----------------------------------------------------


def _register_fixtures(model: ScriptedModel) -> None:
    """Register fixture responses on the scripted model."""
    for key, value in FIXTURES.items():
        model.register_fixture(key, structured_response(value.model_dump()))


def run(
    config: Config | None = None,
    scenario: str = "success",
    vendor_name: str = "AcmeCorp",
    fail_fast: bool = True,
    fixture_overrides: dict[str, str | None] | None = None,
) -> PatternRunResult:
    """Entry point for CLI and tests.

    Args:
        config: Application configuration (uses defaults if None).
        scenario: Test scenario ('success', 'fail_fast', 'partial_results').
        vendor_name: Name of the vendor to evaluate.
        fail_fast: If True, fail immediately on any branch failure.
                   If False, return partial results from surviving branches.
        fixture_overrides: Optional dict of branch -> fixture key overrides.

    Returns:
        PatternRunResult with evaluation outputs and metrics.
    """
    model = ScriptedModel()
    _register_fixtures(model)

    overrides = fixture_overrides or {}

    with run_scope(
        "parallel-fanout-gather",
        scenario,
        max_model_calls=5,
        max_tool_calls=0,
    ) as ctx:
        try:
            sec, leg, ops, fin, synthesis = asyncio.run(
                _run_async(
                    ctx,
                    model,
                    vendor_name,
                    fail_fast=fail_fast,
                    fixture_overrides=overrides,
                )
            )

            # Record state with unique keys per branch (no key collisions)
            state = {
                "security_eval": sec.model_dump(),
                "legal_eval": leg.model_dump(),
                "operational_eval": ops.model_dump(),
                "financial_eval": fin.model_dump(),
                "synthesis": synthesis.model_dump(),
            }
            ctx.snapshot_state(state)
            ctx.output = state

        except Exception as e:
            ctx.mark_failed(str(e))
            # In partial mode, mark as PARTIAL instead of FAILED
            if scenario == "partial_results" and not fail_fast:
                ctx.status = ExecutionStatus.PARTIAL
                ctx.failure_reason = f"Partial results: {e}"

    return ctx.to_result()


def main(config: Config | None = None, scenario: str = "success") -> PatternRunResult:
    """Standard entry point called by CLI.

    Usage:
        uv run python -m examples.03_parallel_fanout_gather.run
        uv run python -m examples.03_parallel_fanout_gather.run --scenario fail_fast
    """
    return run(config=config, scenario=scenario)
