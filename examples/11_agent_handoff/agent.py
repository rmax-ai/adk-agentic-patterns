"""Pattern 11: Agent Handoff.

Scenario: Support agent transfers conversation to a refund specialist.
- Preserve only necessary context (context minimisation)
- Explicit handoff reason
- Receiving agent has narrower permissions
- Handoff audit record
- Rejected handoff fallback
- Test context minimisation
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from adk_patterns.contracts import ExecutionStatus, PatternRunResult, ToolInvocationRecord
from adk_patterns.config import Config
from adk_patterns.models import ScriptedModel, structured_response
from adk_patterns.shared import RunContext, run_scope

# =============================================================================
# Contracts
# =============================================================================


class HandoffRequest(BaseModel):
    """Handoff request issued by a source agent to a target specialist."""

    reason: str = Field(description="Explicit explanation of why the handoff is needed")
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Minimised context passed from source to receiving agent",
    )
    from_agent: str = Field(description="Source agent identifier (e.g. 'support')")
    to_agent: str = Field(description="Target agent identifier (e.g. 'refund_specialist')")


class HandoffResponse(BaseModel):
    """Response from the receiving agent accepting or rejecting a handoff."""

    accepted: bool = Field(description="Whether the receiving agent accepts the handoff")
    reason: str = Field(description="Human-readable explanation for the decision")


# =============================================================================
# Constants
# =============================================================================

SUPPORT_AGENT = "support"
REFUND_AGENT = "refund_specialist"

REQUEST_TEXTS: dict[str, str] = {
    "handoff_accepted": "I was overcharged on my last invoice and need a refund.",
    "handoff_rejected": "I was overcharged on my last invoice and need a refund.",
    "context_minimization": "I was overcharged on my last invoice and need a refund.",
}

# Keys that are permissible to transfer
RELEVANT_CONTEXT_KEYS: set[str] = {
    "customer_id",
    "invoice_id",
    "issue_type",
    "request_text",
    "refund_amount",
}

FULL_CONTEXT_EXAMPLE: dict[str, Any] = {
    "customer_id": "CUST-001",
    "customer_name": "Alice Johnson",
    "customer_email": "alice@example.com",
    "invoice_id": "INV-001",
    "invoice_amount": 149.99,
    "issue_type": "refund",
    "request_text": "I was overcharged on my last invoice and need a refund.",
    "internal_notes": "Customer has called 3 times this week",
    "agent_session_id": "sess_abc123",
    "support_tier": "tier_1",
}

# =============================================================================
# Fixtures
# =============================================================================

HANDOFF_REQUEST_FIXTURES: dict[str, HandoffRequest] = {
    "support_handoff_refund": HandoffRequest(
        reason="Customer is requesting a refund for an overcharge on invoice INV-001",
        context={
            "customer_id": "CUST-001",
            "invoice_id": "INV-001",
            "issue_type": "refund",
            "request_text": "I was overcharged on my last invoice and need a refund.",
        },
        from_agent="support",
        to_agent="refund_specialist",
    ),
    "support_no_handoff": HandoffRequest(
        reason="Customer issue is within support scope — no handoff needed",
        context={
            "customer_id": "CUST-001",
            "issue_type": "general_inquiry",
            "request_text": "I need help finding my account settings.",
        },
        from_agent="support",
        to_agent="refund_specialist",
    ),
}

HANDOFF_RESPONSE_FIXTURES: dict[str, HandoffResponse] = {
    "refund_accept": HandoffResponse(
        accepted=True,
        reason="Refund specialist confirms eligibility and accepts the transfer",
    ),
    "refund_reject": HandoffResponse(
        accepted=False,
        reason="Invoice INV-001 is outside the 30-day refund window — handoff rejected",
    ),
}


def minimise_context(full: dict[str, Any]) -> dict[str, Any]:
    """Strip irrelevant keys from context before handoff."""
    return {k: v for k, v in full.items() if k in RELEVANT_CONTEXT_KEYS}


# =============================================================================
# Mock tools
# =============================================================================


def _lookup_customer(ctx: RunContext, customer_id: str) -> dict[str, object]:
    """Look up a customer record by ID."""
    ctx.audit("support_tool", "tool_call", resource=f"customer:{customer_id}")
    return {
        "customer_id": customer_id,
        "name": "Alice Johnson",
        "email": "alice@example.com",
        "tier": "premium",
    }


def _escalate(ctx: RunContext, customer_id: str, reason: str) -> dict[str, object]:
    """Escalate a customer issue to a human supervisor."""
    ctx.audit("support_tool", "tool_call", resource=f"escalate:{customer_id}")
    return {
        "customer_id": customer_id,
        "reason": reason,
        "status": "escalated",
        "priority": "high",
    }


def _lookup_refund(ctx: RunContext, invoice_id: str) -> dict[str, object]:
    """Look up refund eligibility for a given invoice."""
    ctx.audit("refund_tool", "tool_call", resource=f"refund_lookup:{invoice_id}")
    return {
        "invoice_id": invoice_id,
        "amount": 149.99,
        "status": "paid",
        "eligible": True,
        "days_since_purchase": 5,
    }


def _process_refund(ctx: RunContext, invoice_id: str, amount: float) -> dict[str, object]:
    """Process a refund for a given invoice and amount."""
    ctx.audit("refund_tool", "tool_call", resource=f"refund_process:{invoice_id}")
    return {
        "invoice_id": invoice_id,
        "refund_amount": amount,
        "status": "processed",
        "estimated_credit_days": "3-5 business days",
    }


# -- Tool registries ----------------------------------------------------------

SUPPORT_TOOLS: dict[str, object] = {
    "lookup_customer": _lookup_customer,
    "escalate": _escalate,
}

REFUND_TOOLS: dict[str, object] = {
    "lookup_refund": _lookup_refund,
    "process_refund": _process_refund,
}

ALL_TOOLS: dict[str, dict[str, object]] = {
    "support": SUPPORT_TOOLS,
    "refund_specialist": REFUND_TOOLS,
}


# -- Permission helpers -------------------------------------------------------


def check_agent_permission(agent: str, tool_name: str) -> bool:
    """Verify an agent is permitted to use a specific tool."""
    allowed = ALL_TOOLS.get(agent, {})
    return tool_name in allowed


def execute_agent_tool(
    ctx: RunContext,
    agent: str,
    tool_name: str,
    **kwargs: object,
) -> object:
    """Execute a tool on behalf of an agent after a permission check."""
    if not check_agent_permission(agent, tool_name):
        msg = f"Agent '{agent}' is not permitted to use tool '{tool_name}'"
        ctx.audit(
            "permission_check",
            "denied",
            resource=f"{agent}:{tool_name}",
            outcome="failure",
            metadata={"error": msg},
        )
        raise PermissionError(msg)

    tool_fn = ALL_TOOLS[agent][tool_name]  # type: ignore[operator]
    result = tool_fn(ctx, **kwargs)  # type: ignore[operator]
    ctx.record_tool_call(
        ToolInvocationRecord(
            tool_name=tool_name,
            validated_arguments=dict(kwargs),
            result_summary=dict(result) if isinstance(result, dict) else {"result": str(result)},
        )
    )
    return result


# =============================================================================
# Phase 1: Support agent processes request
# =============================================================================


def support_process(
    ctx: RunContext,
    model: ScriptedModel,
    request_text: str,
    fixture_key: str,
) -> HandoffRequest | None:
    """Support agent processes customer request and decides on handoff.

    Returns a HandoffRequest if handoff to refund specialist is needed,
    or None if the support agent can handle it directly.
    """
    ctx.audit("support_agent", "model_call", resource="support_processing")

    response = model.invoke(
        system_instruction=(
            "You are a support agent. Determine whether the customer request "
            "requires a refund specialist handoff. If the customer explicitly "
            "requests a refund or mentions overcharge/invoice issues, generate "
            "a HandoffRequest. Otherwise return null."
        ),
        messages=[{"role": "user", "content": f"__FIXTURE__:{fixture_key} {request_text}"}],
    )

    ctx.record_model_call(tokens=response.usage.total_tokens)
    ctx.audit("support_agent", "model_response", outcome="success")

    if response.structured_output and "reason" in response.structured_output:
        return HandoffRequest(**response.structured_output)

    # Fallback: check fixtures directly
    fixture = HANDOFF_REQUEST_FIXTURES.get(fixture_key)
    if fixture and fixture.from_agent == "support":
        return fixture

    return None


# =============================================================================
# Phase 2: Refund specialist evaluates handoff
# =============================================================================


def refund_evaluate(
    ctx: RunContext,
    model: ScriptedModel,
    handoff_request: HandoffRequest,
    fixture_key: str,
) -> HandoffResponse:
    """Refund specialist evaluates the handoff request and accepts or rejects."""
    ctx.audit(
        "refund_specialist",
        "model_call",
        resource="handoff_evaluation",
        metadata={
            "from_agent": handoff_request.from_agent,
            "reason": handoff_request.reason,
        },
    )

    eval_prompt = (
        f"Handoff request from {handoff_request.from_agent}: {handoff_request.reason}\n"
        f"Context: {handoff_request.context}\n"
        "Evaluate whether to accept this handoff. "
        "Return a HandoffResponse with accepted=true or false and a reason."
    )

    response = model.invoke(
        system_instruction=(
            "You are a refund specialist. Evaluate handoff requests and decide "
            "whether to accept the transfer based on the provided context."
        ),
        messages=[{"role": "user", "content": f"__FIXTURE__:{fixture_key} {eval_prompt}"}],
    )

    ctx.record_model_call(tokens=response.usage.total_tokens)
    ctx.audit("refund_specialist", "model_response", outcome="success")

    if response.structured_output:
        return HandoffResponse(**response.structured_output)

    # Fallback to fixtures
    fixture = HANDOFF_RESPONSE_FIXTURES.get(fixture_key)
    if fixture:
        return fixture

    return HandoffResponse(accepted=False, reason="Unable to evaluate handoff request")


# =============================================================================
# Phase 3a: Handle with refund specialist
# =============================================================================


def handle_refund(
    ctx: RunContext,
    handoff_request: HandoffRequest,
) -> dict[str, object]:
    """Execute refund specialist tools to process the refund."""
    ctx.audit("refund_specialist", "handle", resource="refund_processing")
    ctx.audit(
        "handoff",
        "accepted",
        resource=f"{handoff_request.from_agent}->{handoff_request.to_agent}",
        metadata={
            "from_agent": handoff_request.from_agent,
            "to_agent": handoff_request.to_agent,
            "reason": handoff_request.reason,
        },
    )

    invoice_id = str(handoff_request.context.get("invoice_id", "INV-001"))

    # Look up refund eligibility
    refund_info = execute_agent_tool(ctx, REFUND_AGENT, "lookup_refund", invoice_id=invoice_id)

    # Process the refund
    amount = float(refund_info.get("amount", 0))  # type: ignore[union-attr]
    refund_result = execute_agent_tool(
        ctx, REFUND_AGENT, "process_refund",
        invoice_id=invoice_id,
        amount=amount,
    )

    return {
        "handoff_accepted": True,
        "specialist": REFUND_AGENT,
        "refund_info": dict(refund_info) if isinstance(refund_info, dict) else {"info": str(refund_info)},
        "refund_result": dict(refund_result) if isinstance(refund_result, dict) else {"result": str(refund_result)},
        "handoff_reason": handoff_request.reason,
    }


# =============================================================================
# Phase 3b: Fallback to support
# =============================================================================


def handle_fallback(
    ctx: RunContext,
    handoff_request: HandoffRequest,
    rejection_reason: str,
) -> dict[str, object]:
    """Support agent handles fallback after handoff rejection."""
    ctx.audit("support_agent", "fallback", resource="handoff_rejected_fallback")
    ctx.audit(
        "handoff",
        "rejected",
        resource=f"{handoff_request.from_agent}->{handoff_request.to_agent}",
        metadata={
            "from_agent": handoff_request.from_agent,
            "to_agent": handoff_request.to_agent,
            "reason": handoff_request.reason,
            "rejection_reason": rejection_reason,
        },
    )

    customer_id = str(handoff_request.context.get("customer_id", "CUST-001"))

    # Escalate the rejected refund request
    escalation = execute_agent_tool(
        ctx, SUPPORT_AGENT, "escalate",
        customer_id=customer_id,
        reason=f"Refund handoff rejected: {rejection_reason}",
    )

    return {
        "handoff_accepted": False,
        "fallback_agent": SUPPORT_AGENT,
        "rejection_reason": rejection_reason,
        "escalation": dict(escalation) if isinstance(escalation, dict) else {"result": str(escalation)},
        "handoff_reason": handoff_request.reason,
    }


# =============================================================================
# Context minimisation
# =============================================================================


def apply_context_minimisation(
    full_context: dict[str, Any],
) -> dict[str, Any]:
    """Strip irrelevant keys from context before transferring to specialist."""
    return minimise_context(full_context)


# =============================================================================
# Main run entry point
# =============================================================================


def run(
    config: Config | None = None,
    scenario: str = "default",
) -> PatternRunResult:
    """Entry point for CLI and tests.

    Args:
        config: Application configuration (uses defaults if None)
        scenario: Test scenario name

    Returns:
        PatternRunResult with conversation_context, handoff_record, refund_result
    """
    model = ScriptedModel()

    # Register handoff request fixtures
    for key, request in HANDOFF_REQUEST_FIXTURES.items():
        model.register_fixture(key, structured_response(request.model_dump()))
    # Register handoff response fixtures
    for key, response in HANDOFF_RESPONSE_FIXTURES.items():
        model.register_fixture(key, structured_response(response.model_dump()))

    # Determine fixture keys based on scenario
    fixture_map: dict[str, tuple[str, str]] = {
        "handoff_accepted": ("support_handoff_refund", "refund_accept"),
        "handoff_rejected": ("support_handoff_refund", "refund_reject"),
        "context_minimization": ("support_handoff_refund", "refund_accept"),
    }

    default_fixtures = fixture_map.get(
        scenario,
        fixture_map["handoff_accepted"],
    )
    support_fixture_key, refund_fixture_key = default_fixtures

    request_text = REQUEST_TEXTS.get(scenario, REQUEST_TEXTS["handoff_accepted"])

    with run_scope("agent-handoff", scenario) as ctx:
        conversation_context: dict[str, Any] = {}

        # Phase 1: Support agent processes request (model call #1)
        handoff_request = support_process(ctx, model, request_text, support_fixture_key)

        if handoff_request is None:
            # No handoff needed — support handles directly
            ctx.audit("support_agent", "handle_directly", outcome="success")
            ctx.output = {
                "conversation_context": {"agent": SUPPORT_AGENT, "status": "handled_directly"},
                "handoff_record": None,
                "refund_result": None,
            }
        else:
            # Apply context minimisation before handoff
            minimised = apply_context_minimisation(handoff_request.context)
            handoff_request.context = minimised

            # Phase 2: Refund specialist evaluates handoff (model call #2)
            handoff_response = refund_evaluate(ctx, model, handoff_request, refund_fixture_key)

            # Build handoff record for audit
            handoff_record: dict[str, object] = {
                "request": handoff_request.model_dump(),
                "response": handoff_response.model_dump(),
            }

            if handoff_response.accepted:
                # Phase 3a: Handle with refund specialist
                refund_result = handle_refund(ctx, handoff_request)
                conversation_context = {"agent": REFUND_AGENT, "status": "refund_handled"}
            else:
                # Phase 3b: Fallback to support
                refund_result = handle_fallback(ctx, handoff_request, handoff_response.reason)
                conversation_context = {"agent": SUPPORT_AGENT, "status": "handoff_fallback"}

            # Snapshot state
            ctx.snapshot_state({
                "conversation_context": conversation_context,
                "handoff_record": handoff_record,
                "refund_result": refund_result,
            })

            ctx.output = {
                "conversation_context": conversation_context,
                "handoff_record": handoff_record,
                "refund_result": refund_result,
            }

    return ctx.to_result()


def main(config: Config | None = None, scenario: str = "default") -> PatternRunResult:
    """Standard entry point called by CLI."""
    return run(config=config, scenario=scenario)
