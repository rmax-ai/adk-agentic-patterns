"""Pattern 21: Budget-Aware Model Routing.

Route simple, medium, complex requests to fake model tiers.
- Complexity classifier (deterministic first)
- Per-tier cost and latency metadata
- Token budget tracking
- Fallback from expensive to cheap on budget exhaustion
- Escalation from cheap to expensive after validation failure
- No infinite escalation (max 2 escalations)
- Calculate cost-per-success
"""

from __future__ import annotations

import sys
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from adk_patterns.contracts import PatternRunResult
from adk_patterns.config import Config
from adk_patterns.models import ScriptedModel, text_response
from adk_patterns.shared import run_scope

# Ensure this example directory is on sys.path (digit-prefixed dirs aren't valid packages)
_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))


# ── Contracts ────────────────────────────────────────────────────────────


class ComplexityClass(str, Enum):
    """Request complexity classification."""

    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


class ModelTier(str, Enum):
    """Model tier selection for routing."""

    CHEAP = "cheap"
    MEDIUM = "medium"
    EXPENSIVE = "expensive"


class RoutingDecision(BaseModel):
    """Decision record for a routing choice."""

    tier: ModelTier = Field(description="Selected model tier")
    reason: str = Field(description="Why this tier was chosen")
    estimated_cost: float = Field(ge=0.0, description="Estimated cost for this tier")
    escalation_count: int = Field(default=0, ge=0, description="Number of escalations attempted")


# Per-tier cost and latency metadata
TIER_METADATA: dict[ModelTier, dict[str, float]] = {
    ModelTier.CHEAP: {"cost_per_call": 0.001, "latency_ms": 50.0},
    ModelTier.MEDIUM: {"cost_per_call": 0.005, "latency_ms": 150.0},
    ModelTier.EXPENSIVE: {"cost_per_call": 0.020, "latency_ms": 500.0},
}

ESCALATION_ORDER: list[ModelTier] = [
    ModelTier.CHEAP,
    ModelTier.MEDIUM,
    ModelTier.EXPENSIVE,
]

MAX_ESCALATIONS = 2


# ── Fixtures ─────────────────────────────────────────────────────────────


CHEAP_FIXTURES = {
    "simple_greeting": text_response(
        "Hello! How can I assist you today?",
        prompt_tokens=10,
        completion_tokens=8,
    ),
    "simple_weather": text_response(
        "What's the weather like?",
        prompt_tokens=10,
        completion_tokens=8,
    ),
    "simple_time": text_response(
        "The current time is 10:30 AM UTC.",
        prompt_tokens=10,
        completion_tokens=10,
    ),
    "simple_fallback": text_response(
        "Sorry, I couldn't process that request.",
        prompt_tokens=10,
        completion_tokens=10,
    ),
    "simple_empty": text_response(
        "",
        prompt_tokens=5,
        completion_tokens=5,
    ),
    "simple_token_heavy": text_response(
        "A" * 5000,
        prompt_tokens=10,
        completion_tokens=5000,
    ),
}

MEDIUM_FIXTURES = {
    "medium_explain": text_response(
        "Let me explain that concept. The idea revolves around several key "
        "principles including modularity, encapsulation, and separation of "
        "concerns. Each of these principles helps manage complexity.",
        prompt_tokens=30,
        completion_tokens=40,
    ),
    "medium_summarize": text_response(
        "The article discusses three main points: first, the importance of "
        "data-driven decision making; second, the role of automation in "
        "reducing operational overhead; and third, the need for continuous "
        "monitoring and observability.",
        prompt_tokens=25,
        completion_tokens=50,
    ),
}

EXPENSIVE_FIXTURES = {
    "complex_analysis": text_response(
        "Based on comprehensive analysis of the provided data, I can identify "
        "several interconnected patterns. The primary finding suggests a "
        "correlation between system latency and cache hit ratios across all "
        "three regions. However, the secondary metrics indicate that "
        "connection pooling may have a more significant impact on overall "
        "performance than previously estimated.",
        prompt_tokens=100,
        completion_tokens=150,
    ),
    "complex_architecture": text_response(
        "For a microservices architecture handling 10K requests per second, "
        "I recommend the following design: Use a message queue for async "
        "communication between services. Implement API Gateway pattern for "
        "request routing and rate limiting.",
        prompt_tokens=150,
        completion_tokens=200,
    ),
}

# Validation registry: False means the fixture is a known invalid response
VALID_RESPONSES = {
    "simple_greeting": True,
    "simple_weather": True,
    "simple_time": True,
    "simple_fallback": False,
    "simple_empty": False,
    "simple_token_heavy": True,
    "medium_explain": True,
    "medium_summarize": True,
    "complex_analysis": True,
    "complex_architecture": True,
}

SIMPLE_REQUEST = "What's the weather like?"
MEDIUM_REQUEST = (
    "Can you explain the key principles of microservices architecture "
    "and how they compare with monolithic designs?"
)
COMPLEX_REQUEST = (
    "We need a comprehensive analysis of our current infrastructure. "
    "Our system handles approximately 10K requests per second across "
    "three geographic regions. We're seeing intermittent latency spikes "
    "in the us-east-1 region during peak hours. What architectural "
    "changes would you recommend to improve reliability and reduce "
    "p99 latency, considering we use a mix of Kubernetes and serverless "
    "deployments?"
)


# ── Deterministic complexity classifier ─────────────────────────────────


def classify_complexity(request_text: str) -> ComplexityClass:
    """Classify request complexity deterministically based on length.

    Simple: < 80 chars
    Medium: 80-200 chars
    Complex: > 200 chars
    """
    length = len(request_text)
    if length < 80:
        return ComplexityClass.SIMPLE
    elif length < 200:
        return ComplexityClass.MEDIUM
    else:
        return ComplexityClass.COMPLEX


# ── Tier routing ────────────────────────────────────────────────────────


def complexity_to_tier(complexity: ComplexityClass) -> ModelTier:
    """Map complexity class to initial model tier."""
    mapping = {
        ComplexityClass.SIMPLE: ModelTier.CHEAP,
        ComplexityClass.MEDIUM: ModelTier.MEDIUM,
        ComplexityClass.COMPLEX: ModelTier.EXPENSIVE,
    }
    return mapping[complexity]


def get_tier_cost(tier: ModelTier) -> float:
    """Get per-call cost for a given tier."""
    return TIER_METADATA[tier]["cost_per_call"]


# ── Model invocation ────────────────────────────────────────────────────


def invoke_model(
    model: ScriptedModel,
    fixture_key: str,
    system_instruction: str = "",
) -> tuple[str, int]:
    """Invoke the model with a fixture key.

    Returns (response_text, total_tokens_used).
    """
    response = model.invoke(
        system_instruction=system_instruction,
        messages=[
            {"role": "user", "content": f"__FIXTURE__:{fixture_key} Process this request."}
        ],
    )
    tokens = response.usage.total_tokens if response.usage else 0
    return response.text, tokens


# ── Validation ──────────────────────────────────────────────────────────


def validate_response(tier: ModelTier, response_text: str, fixture_key: str) -> bool:
    """Validate model response for the given tier.

    A response is valid if it has non-empty text and the fixture key
    is registered as a known valid response.
    """
    if not response_text.strip():
        return False
    known_valid = VALID_RESPONSES.get(fixture_key, True)
    return known_valid


# ── Escalation logic ────────────────────────────────────────────────────


def next_escalation_tier(current: ModelTier) -> ModelTier | None:
    """Get the next higher tier for escalation.

    Returns None if already at max tier.
    """
    idx = ESCALATION_ORDER.index(current)
    if idx + 1 >= len(ESCALATION_ORDER):
        return None
    return ESCALATION_ORDER[idx + 1]


def next_fallback_tier(current: ModelTier) -> ModelTier | None:
    """Get a cheaper tier for fallback.

    Returns None if already at minimum tier.
    """
    idx = ESCALATION_ORDER.index(current)
    if idx - 1 < 0:
        return None
    return ESCALATION_ORDER[idx - 1]


# ── Fixture key selection ───────────────────────────────────────────────


def get_fixture_key(tier: ModelTier, request_text: str) -> str:
    """Select a fixture key based on tier and request content."""
    if tier == ModelTier.CHEAP:
        if "empty" in request_text.lower() or "fail" in request_text.lower() or "validation" in request_text.lower():
            return "simple_empty"
        if "weather" in request_text.lower():
            return "simple_weather"
        if "time" in request_text.lower():
            return "simple_time"
        if "hello" in request_text.lower() or "hi" in request_text.lower():
            return "simple_greeting"
        if "token" in request_text.lower() or "heavy" in request_text.lower():
            return "simple_token_heavy"
        return "simple_greeting"
    elif tier == ModelTier.MEDIUM:
        if "explain" in request_text.lower():
            return "medium_explain"
        return "medium_summarize"
    else:  # expensive
        if "architecture" in request_text.lower():
            return "complex_architecture"
        return "complex_analysis"


# ── Main routing pipeline ───────────────────────────────────────────────


def run(
    config: Config | None = None,
    scenario: str = "default",
    request_text: str | None = None,
) -> PatternRunResult:
    """Execute budget-aware model routing.

    Args:
        config: Application configuration (uses defaults if None).
        scenario: Test scenario name.
        request_text: Input text to route. Uses fixture defaults if None.

    Returns:
        PatternRunResult with routing decision, cost, and result.
    """
    # Build model with all fixtures registered
    model = ScriptedModel()
    model.register_fixtures(CHEAP_FIXTURES)
    model.register_fixtures(MEDIUM_FIXTURES)
    model.register_fixtures(EXPENSIVE_FIXTURES)

    # Pick request text
    request_texts = {
        "simple": SIMPLE_REQUEST,
        "medium": MEDIUM_REQUEST,
        "complex": COMPLEX_REQUEST,
        "default": SIMPLE_REQUEST,
        "validation_failure": "fail_validation_on_cheap",
        "budget_exhaustion": "heavy_token_request_expensive",
    }

    request = request_text or request_texts.get(scenario, SIMPLE_REQUEST)

    with run_scope(
        "budget-aware-model-routing",
        scenario,
        max_model_calls=4,
        max_synthetic_tokens=5000,
    ) as ctx:
        # ── Step 1: Classify complexity ──────────────────────────────────
        complexity = classify_complexity(request)
        ctx.audit("classifier", "classify", resource=f"complexity={complexity.value}")

        # ── Step 2: Determine initial tier ───────────────────────────────
        current_tier = complexity_to_tier(complexity)
        ctx.audit(
            "router",
            "route",
            resource=f"tier={current_tier.value}",
            metadata={"complexity": complexity.value},
        )

        routing_decision = RoutingDecision(
            tier=current_tier,
            reason=f"Initial route based on {complexity.value} classification",
            estimated_cost=get_tier_cost(current_tier),
            escalation_count=0,
        )
        ctx.snapshot_state({"routing_decision": routing_decision.model_dump()})

        # ── Step 3: Execute with budget tracking and escalation ──────────
        result_text = ""
        total_cost = 0.0
        escalation_count = 0
        final_tier = current_tier
        success = False

        for attempt in range(MAX_ESCALATIONS + 1):  # Max 2 escalations = max 3 attempts
            # Check budget before each invocation
            if ctx.check_budget() is not None:
                ctx.audit(
                    "budget",
                    "exhaustion",
                    outcome="failure",
                    metadata={
                        "model_calls": ctx.model_calls,
                        "synthetic_tokens": ctx.synthetic_tokens,
                    },
                )
                # Fallback: try cheaper tier
                cheaper = next_fallback_tier(final_tier)
                if cheaper is not None:
                    final_tier = cheaper
                    ctx.audit(
                        "router",
                        "fallback_to_cheap",
                        resource=f"tier={cheaper.value}",
                        metadata={"reason": "budget_exhausted"},
                    )
                    routing_decision = RoutingDecision(
                        tier=final_tier,
                        reason=f"Budget exhausted, fell back to {final_tier.value}",
                        estimated_cost=get_tier_cost(final_tier),
                        escalation_count=escalation_count,
                    )
                    ctx.snapshot_state({"routing_decision": routing_decision.model_dump()})
                else:
                    ctx.mark_budget_exhausted()
                    ctx.output = {
                        "routing_decision": routing_decision.model_dump(),
                        "model_tier": final_tier.value,
                        "cost": total_cost,
                        "result": "budget_exhausted",
                    }
                    return ctx.to_result()

            # Invoke the model
            fixture_key = get_fixture_key(final_tier, request)
            ctx.audit(
                "model",
                "invoke",
                resource=f"tier={final_tier.value},fixture={fixture_key}",
            )

            response_text, actual_tokens = invoke_model(model, fixture_key)
            ctx.record_model_call(tokens=actual_tokens)
            total_cost += get_tier_cost(final_tier)

            ctx.audit(
                "model",
                "response",
                outcome="success",
                metadata={"tier": final_tier.value, "response_length": len(response_text)},
            )

            # Validate response
            is_valid = validate_response(final_tier, response_text, fixture_key)

            if is_valid:
                result_text = response_text
                success = True
                ctx.audit("validator", "validation_passed", resource=f"tier={final_tier.value}")
                break
            else:
                ctx.audit(
                    "validator",
                    "validation_failed",
                    outcome="failure",
                    metadata={"tier": final_tier.value, "escalation": escalation_count + 1},
                )

                # Escalate to higher tier
                escalation_count += 1
                if escalation_count > MAX_ESCALATIONS:
                    ctx.audit(
                        "router",
                        "max_escalations_reached",
                        outcome="failure",
                        metadata={"escalation_count": escalation_count},
                    )
                    ctx.mark_failed(
                        f"Max escalations ({MAX_ESCALATIONS}) reached. "
                        f"Could not get valid response."
                    )
                    ctx.output = {
                        "routing_decision": routing_decision.model_dump(),
                        "model_tier": final_tier.value,
                        "cost": total_cost,
                        "result": result_text,
                    }
                    return ctx.to_result()

                next_tier = next_escalation_tier(final_tier)
                if next_tier is None:
                    ctx.mark_failed("No further escalation tier available.")
                    ctx.output = {
                        "routing_decision": routing_decision.model_dump(),
                        "model_tier": final_tier.value,
                        "cost": total_cost,
                        "result": result_text,
                    }
                    return ctx.to_result()

                ctx.audit(
                    "router",
                    "escalate",
                    resource=f"from={final_tier.value},to={next_tier.value}",
                    metadata={"escalation_count": escalation_count},
                )
                final_tier = next_tier
                routing_decision = RoutingDecision(
                    tier=final_tier,
                    reason=f"Escalated after validation failure (attempt {escalation_count})",
                    estimated_cost=get_tier_cost(final_tier),
                    escalation_count=escalation_count,
                )
                ctx.snapshot_state({"routing_decision": routing_decision.model_dump()})

        # ── Step 4: Build final output ───────────────────────────────────
        cost_per_success = total_cost if success else 0.0

        ctx.output = {
            "routing_decision": routing_decision.model_dump(),
            "model_tier": final_tier.value,
            "cost": total_cost,
            "result": result_text,
            "cost_per_success": cost_per_success,
            "success": success,
        }
        ctx.snapshot_state(ctx.output)

    # Add cost_per_success to metrics
    result = ctx.to_result()
    result.metrics["cost_per_success"] = cost_per_success
    return result


def main(config: Config | None = None, scenario: str = "default") -> PatternRunResult:
    """Standard entry point called by CLI."""
    return run(config=config, scenario=scenario)
