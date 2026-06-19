"""Pattern 02: Router-Specialist.

Scenario: Route customer requests to billing, account, or technical specialists.

Demonstrates both model-driven and rule-driven router variants with:
- Typed routing verdict with confidence threshold (Pydantic model)
- Confidence below threshold (0.6) → deterministic fallback to 'general'
- Isolated tool sets per specialist
- Router confusion-matrix handling
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from adk_patterns.contracts import PatternRunResult, ToolInvocationRecord
from adk_patterns.config import Config
from adk_patterns.models import ScriptedModel, structured_response
from adk_patterns.shared import RunContext, run_scope


# -- Contracts ---------------------------------------------------------------


class RouterVerdict(BaseModel):
    """Routing decision produced by the model with confidence score.

    When confidence falls below the threshold (0.6), a deterministic
    fallback re-routes to the 'general' specialist.
    """

    route: str = Field(
        description="Target specialist route: billing, account, technical, or general",
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence in the routing decision (0.0–1.0)",
    )
    reasoning: str = Field(
        default="", description="Brief explanation of the routing decision",
    )


class SpecialistOutput(BaseModel):
    """Output produced by a specialist agent after handling a routed request."""

    specialist: str = Field(description="Which specialist handled the request")
    response: str = Field(description="Response from the specialist")
    tools_used: list[str] = Field(
        default_factory=list,
        description="Tool names invoked by this specialist",
    )


# -- Fixtures ----------------------------------------------------------------

CONFIDENCE_THRESHOLD = 0.6

ROUTER_FIXTURES: dict[str, RouterVerdict] = {
    "billing_route": RouterVerdict(
        route="billing",
        confidence=0.92,
        reasoning="Customer mentions overcharge and invoice dispute",
    ),
    "account_route": RouterVerdict(
        route="account",
        confidence=0.89,
        reasoning="Customer cannot log in and needs password reset",
    ),
    "technical_route": RouterVerdict(
        route="technical",
        confidence=0.91,
        reasoning="Customer reports API errors and system downtime",
    ),
    "low_confidence": RouterVerdict(
        route="billing",
        confidence=0.45,
        reasoning="Weak signal — customer mentions 'pay' vaguely",
    ),
    "unknown_route": RouterVerdict(
        route="unknown_topic",
        confidence=0.35,
        reasoning="Customer query does not match any known category",
    ),
    "ambiguous": RouterVerdict(
        route="general",
        confidence=0.40,
        reasoning="Query spans billing, account, and technical topics",
    ),
}

# Confusion-matrix test set — model routes to wrong specialist
CONFUSION_MATRIX: dict[str, tuple[str, RouterVerdict]] = {
    "billing_as_account": (
        "billing",
        RouterVerdict(
            route="account",
            confidence=0.78,
            reasoning="Model misrouted — customer has billing question",
        ),
    ),
    "account_as_technical": (
        "account",
        RouterVerdict(
            route="technical",
            confidence=0.81,
            reasoning="Model misrouted — customer has account issue",
        ),
    ),
    "technical_as_billing": (
        "technical",
        RouterVerdict(
            route="billing",
            confidence=0.75,
            reasoning="Model misrouted — customer has technical issue",
        ),
    ),
}

SPECIALIST_FIXTURES: dict[str, SpecialistOutput] = {
    "billing_handled": SpecialistOutput(
        specialist="billing",
        response="I've reviewed your invoice and processed a refund for the overcharge. You should see the credit within 3\u20135 business days.",
        tools_used=["lookup_invoice", "process_refund"],
    ),
    "account_handled": SpecialistOutput(
        specialist="account",
        response="I've reset your password. Please check your email for the temporary password and login instructions.",
        tools_used=["reset_password", "send_verification_email"],
    ),
    "technical_handled": SpecialistOutput(
        specialist="technical",
        response="I checked the API status. The 500 errors were caused by a temporary outage that has been resolved. Please retry your requests.",
        tools_used=["check_api_status", "query_logs"],
    ),
    "general_handled": SpecialistOutput(
        specialist="general",
        response="Thank you for your inquiry. I've forwarded your request to the appropriate team for review. A representative will follow up.",
        tools_used=[],
    ),
}

REQUEST_TEXTS: dict[str, str] = {
    "billing_route": "I was overcharged on my last invoice and need a refund.",
    "account_route": "I can't log into my account after the password reset.",
    "technical_route": "Your API keeps returning 500 errors and timing out.",
    "low_confidence": "Pay.",
    "unknown_route": "What is the meaning of life?",
    "ambiguous": "I have questions about my bill and also can't access the dashboard.",
}


# -- Mock tools (isolated per specialist) ------------------------------------


def _lookup_invoice(ctx: RunContext, invoice_id: str) -> dict[str, object]:
    ctx.audit("billing_tool", "tool_call", resource=f"invoice:{invoice_id}")
    return {"invoice_id": invoice_id, "amount": 149.99, "status": "paid", "overcharged": True}


def _process_refund(ctx: RunContext, invoice_id: str, amount: float) -> dict[str, object]:
    ctx.audit("billing_tool", "tool_call", resource=f"refund:{invoice_id}")
    return {"invoice_id": invoice_id, "refund_amount": amount, "status": "processed", "estimated_credit_days": "3-5"}


def _reset_password(ctx: RunContext, username: str) -> dict[str, object]:
    ctx.audit("account_tool", "tool_call", resource=f"password_reset:{username}")
    return {"username": username, "status": "reset_initiated", "email_sent": True}


def _send_verification_email(ctx: RunContext, email: str) -> dict[str, object]:
    ctx.audit("account_tool", "tool_call", resource=f"verification_email:{email}")
    return {"email": email, "status": "sent"}


def _check_api_status(ctx: RunContext, service: str) -> dict[str, object]:
    ctx.audit("technical_tool", "tool_call", resource=f"api_status:{service}")
    return {"service": service, "status": "operational", "recent_incidents": ["500 errors from 14:30-14:45 UTC"], "uptime_pct": 99.95}


def _query_logs(ctx: RunContext, service: str, timeframe: str) -> dict[str, object]:
    ctx.audit("technical_tool", "tool_call", resource=f"logs:{service}:{timeframe}")
    return {
        "service": service,
        "timeframe": timeframe,
        "entries": [
            {"timestamp": "14:30:01", "level": "ERROR", "message": "HTTP 500 on /api/v1/orders"},
            {"timestamp": "14:35:12", "level": "ERROR", "message": "HTTP 500 on /api/v1/users"},
            {"timestamp": "14:45:00", "level": "INFO", "message": "Service restored"},
        ],
    }


# Tool registry — each specialist has its own isolated set
# Type: dict[str, dict[str, Callable[..., dict[str, object]]]]
SPECIALIST_TOOL_MAP: dict[str, dict[str, object]] = {
    "billing": {"lookup_invoice": _lookup_invoice, "process_refund": _process_refund},
    "account": {"reset_password": _reset_password, "send_verification_email": _send_verification_email},
    "technical": {"check_api_status": _check_api_status, "query_logs": _query_logs},
    "general": {},
}


# -- Tool helpers ------------------------------------------------------------


def check_tool_permission(specialist: str, tool_name: str) -> bool:
    """Verify a specialist is allowed to use a specific tool."""
    allowed_tools = SPECIALIST_TOOL_MAP.get(specialist, {})
    return tool_name in allowed_tools


def execute_specialist_tool(
    ctx: RunContext,
    specialist: str,
    tool_name: str,
    **kwargs: object,
) -> object:
    """Execute a tool on behalf of a specialist after permission check."""
    if not check_tool_permission(specialist, tool_name):
        error_msg = f"Specialist '{specialist}' is not permitted to use tool '{tool_name}'"
        ctx.audit("permission_check", "denied", resource=f"{specialist}:{tool_name}", outcome="failure")
        raise PermissionError(error_msg)

    tool_fn = SPECIALIST_TOOL_MAP[specialist][tool_name]
    result = tool_fn(ctx, **kwargs)  # type: ignore[operator]
    ctx.record_tool_call(
        ToolInvocationRecord(
            tool_name=tool_name,
            validated_arguments=dict(kwargs),
            result_summary=dict(result) if isinstance(result, dict) else {"result": str(result)},
        )
    )
    return result


# -- Model-driven router ----------------------------------------------------


def model_driven_route(
    ctx: RunContext,
    model: ScriptedModel,
    request_text: str,
    fixture_key: str,
) -> RouterVerdict:
    """Use the model to determine the routing verdict."""
    ctx.audit("router", "model_call", resource="routing_classification")

    response = model.invoke(
        system_instruction=(
            "Classify the customer support request into one of these routes: "
            "billing, account, technical, or general. "
            "Return a structured verdict with route, confidence, and reasoning."
        ),
        messages=[{"role": "user", "content": f"__FIXTURE__:{fixture_key} {request_text}"}],
    )

    ctx.record_model_call(tokens=response.usage.total_tokens)
    ctx.audit("router", "model_response", outcome="success")

    if response.structured_output:
        verdict = RouterVerdict(**response.structured_output)
    else:
        verdict = ROUTER_FIXTURES.get(fixture_key, RouterVerdict(
            route="general", confidence=0.0, reasoning="Fallback — no fixture match",
        ))

    # Apply confidence threshold: low confidence routes to general
    if verdict.confidence < CONFIDENCE_THRESHOLD:
        ctx.audit(
            "router", "confidence_fallback",
            resource=f"route:{verdict.route}",
            outcome="rerouted",
            metadata={
                "original_route": verdict.route,
                "confidence": verdict.confidence,
                "threshold": CONFIDENCE_THRESHOLD,
            },
        )
        verdict.route = "general"

    ctx.snapshot_state({"route_verdict": verdict.model_dump()})
    return verdict


# -- Rule-driven router (deterministic, no model call) ----------------------


def rule_driven_route(ctx: RunContext, request_text: str) -> RouterVerdict:
    """Deterministic keyword-based router without a model call."""
    ctx.audit("rule_router", "keyword_match", resource="routing_classification")

    text_lower = request_text.lower()

    keywords: dict[str, list[str]] = {
        "billing": ["invoice", "bill", "charge", "overcharge", "refund", "payment", "cost", "price"],
        "account": ["login", "password", "account", "reset", "sign in", "register", "username"],
        "technical": ["api", "error", "timeout", "500", "crash", "bug", "downtime", "server"],
    }

    scores: dict[str, int] = {}
    for route, route_keywords in keywords.items():
        scores[route] = sum(1 for kw in route_keywords if kw in text_lower)

    max_score = max(scores.values()) if scores else 0
    matched_routes = [r for r, s in scores.items() if s == max_score and s > 0]

    if not matched_routes:
        verdict = RouterVerdict(
            route="general",
            confidence=0.0,
            reasoning="No keywords matched — falling back to general",
        )
    elif len(matched_routes) == 1:
        route = matched_routes[0]
        confidence = min(0.5 + max_score * 0.15, 0.99)
        verdict = RouterVerdict(
            route=route,
            confidence=confidence,
            reasoning=f"Matched {max_score} keyword(s) for {route}",
        )
    else:
        verdict = RouterVerdict(
            route="general",
            confidence=0.3,
            reasoning=f"Multiple routes tied ({', '.join(matched_routes)}) — falling back",
        )

    ctx.snapshot_state({"route_verdict": verdict.model_dump()})
    ctx.audit("rule_router", "result", resource=f"route:{verdict.route}",
              metadata={"confidence": verdict.confidence, "reasoning": verdict.reasoning})
    return verdict


# -- Specialist handler -----------------------------------------------------


def handle_with_specialist(
    ctx: RunContext,
    specialist: str,
    request_text: str,
    verdict: RouterVerdict,
) -> SpecialistOutput:
    """Route the request to the appropriate specialist and get a response."""
    ctx.audit("specialist", "dispatch", resource=f"specialist:{specialist}")

    # Use fixture if available
    fixture_key = f"{specialist}_handled"
    if fixture_key in SPECIALIST_FIXTURES:
        output = SPECIALIST_FIXTURES[fixture_key].model_copy()
    else:
        output = SpecialistOutput(
            specialist=specialist,
            response=f"Handled by {specialist} specialist.",
            tools_used=[],
        )

    # Execute specialist tools
    tools_used: list[str] = []
    if specialist == "billing":
        for tool_name in ["lookup_invoice", "process_refund"]:
            try:
                kwargs = {"invoice_id": "INV-001"} if tool_name == "lookup_invoice" else {"invoice_id": "INV-001", "amount": 49.99}
                execute_specialist_tool(ctx, specialist, tool_name, **kwargs)
                tools_used.append(tool_name)
            except PermissionError:
                pass
    elif specialist == "account":
        for tool_name in ["reset_password", "send_verification_email"]:
            try:
                kwargs = {"username": "customer"} if tool_name == "reset_password" else {"email": "customer@example.com"}
                execute_specialist_tool(ctx, specialist, tool_name, **kwargs)
                tools_used.append(tool_name)
            except PermissionError:
                pass
    elif specialist == "technical":
        for tool_name in ["check_api_status", "query_logs"]:
            try:
                kwargs = {"service": "api-v1"} if tool_name == "check_api_status" else {"service": "api-v1", "timeframe": "last_1h"}
                execute_specialist_tool(ctx, specialist, tool_name, **kwargs)
                tools_used.append(tool_name)
            except PermissionError:
                pass

    output.tools_used = tools_used
    ctx.snapshot_state({"specialist_output": output.model_dump()})
    return output


# -- Main run entry point ---------------------------------------------------


def run(
    config: Config | None = None,
    scenario: str = "default",
    use_rule_router: bool = False,
) -> PatternRunResult:
    """Entry point for CLI and tests.

    Args:
        config: Application configuration (uses defaults if None)
        scenario: Test scenario name
        use_rule_router: If True, use rule-driven router instead of model-driven

    Returns:
        PatternRunResult with routing verdict and specialist output
    """
    model = ScriptedModel()

    # Register routing verdict fixtures
    for key, verdict in ROUTER_FIXTURES.items():
        model.register_fixture(key, structured_response(verdict.model_dump()))

    fixture_key = scenario if scenario in ROUTER_FIXTURES else "billing_route"
    request_text = REQUEST_TEXTS.get(fixture_key, REQUEST_TEXTS["billing_route"])

    with run_scope("router-specialist", scenario) as ctx:
        # Phase 1: Route the request
        if use_rule_router:
            verdict = rule_driven_route(ctx, request_text)
        else:
            verdict = model_driven_route(ctx, model, request_text, fixture_key)

        # Phase 2: Handle with specialist (applying fallback if needed)
        specialist = verdict.route
        output = handle_with_specialist(ctx, specialist, request_text, verdict)

        ctx.output = {
            "route_verdict": verdict.model_dump(),
            "specialist_output": output.model_dump(),
        }
        ctx.snapshot_state({
            "route_verdict": verdict.model_dump(),
            "specialist_output": output.model_dump(),
        })

    return ctx.to_result()


def main(config: Config | None = None, scenario: str = "default") -> PatternRunResult:
    """Standard entry point called by CLI."""
    return run(config=config, scenario=scenario)
