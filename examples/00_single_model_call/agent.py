"""Pattern 00: Single Structured Model Call.

Scenario: Classify a support request into a typed category.

This is the simplest baseline — one model invocation, no tools, no loop.
Establishes the minimum viable pattern structure.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from adk_patterns.contracts import PatternRunResult
from adk_patterns.config import Config
from adk_patterns.models import ScriptedModel, structured_response
from adk_patterns.shared import RunContext, run_scope


class SupportCategory(str):
    BILLING = "billing"
    ACCOUNT = "account"
    TECHNICAL = "technical"
    GENERAL = "general"


class ClassificationResult(BaseModel):
    """Typed classification output — the model must conform to this schema."""

    category: str = Field(description="Support category: billing, account, technical, general")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score")
    reasoning: str = Field(description="Brief explanation for the classification")


# -- Fixtures ---------------------------------------------------------------

FIXTURES = {
    "billing_issue": ClassificationResult(
        category="billing", confidence=0.95, reasoning="Customer mentions overcharge and invoice"
    ),
    "account_issue": ClassificationResult(
        category="account", confidence=0.90, reasoning="Customer mentions login and password reset"
    ),
    "technical_issue": ClassificationResult(
        category="technical", confidence=0.88, reasoning="Customer reports API errors and timeouts"
    ),
    "ambiguous": ClassificationResult(
        category="general", confidence=0.45, reasoning="Query spans multiple categories without clear signal"
    ),
}


def classify_request(
    ctx: RunContext,
    model: ScriptedModel,
    request_text: str,
    fixture_key: str,
) -> ClassificationResult:
    """Classify a support request using a single model call.

    Args:
        ctx: Run context for audit and budget tracking
        model: Scripted model with pre-registered fixtures
        request_text: The customer's support request text
        fixture_key: Fixture key for deterministic response
    """
    ctx.audit("classifier", "model_call", resource="support_request")

    response = model.invoke(
        system_instruction="Classify the support request into a typed category.",
        messages=[{"role": "user", "content": f"__FIXTURE__:{fixture_key} {request_text}"}],
    )

    ctx.record_model_call(tokens=response.usage.total_tokens)
    ctx.audit("classifier", "model_response", outcome="success")

    if response.structured_output:
        return ClassificationResult(**response.structured_output)

    # Fallback: parse text as structured output via fixture lookup
    result = FIXTURES.get(fixture_key)
    if result is None:
        ctx.mark_failed(f"No fixture for key: {fixture_key}")
        raise ValueError(f"No fixture for key: {fixture_key}")

    return result


def run(config: Config | None = None, scenario: str = "default") -> PatternRunResult:
    """Entry point for CLI and tests.

    Args:
        config: Application configuration (uses defaults if None)
        scenario: Test scenario override (default, billing_issue, etc.)
    """
    model = ScriptedModel()
    for key, result in FIXTURES.items():
        model.register_fixture(key, structured_response(result.model_dump()))

    fixture_key = scenario if scenario in FIXTURES else "billing_issue"
    request_texts = {
        "billing_issue": "I was overcharged on my last invoice and need a refund.",
        "account_issue": "I can't log into my account after the password reset.",
        "technical_issue": "Your API keeps returning 500 errors and timing out.",
        "ambiguous": "I have questions about my bill and also can't access the dashboard.",
    }

    with run_scope("single-model-call", scenario) as ctx:
        result = classify_request(
            ctx,
            model,
            request_texts.get(fixture_key, request_texts["billing_issue"]),
            fixture_key,
        )
        ctx.output = result.model_dump()
        ctx.snapshot_state({"classification": result.model_dump()})

    return ctx.to_result()


def main(config: Config | None = None, scenario: str = "default") -> PatternRunResult:
    """Standard entry point called by CLI."""
    return run(config=config, scenario=scenario)
