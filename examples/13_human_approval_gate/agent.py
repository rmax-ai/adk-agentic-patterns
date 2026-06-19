"""Pattern 13: Human Approval Gate.

Scenario: Agent proposes a refund but cannot execute it without human approval.
Workflow suspends in a pending/checkpoint state, then resumes via
approve/reject/timeout/amend paths. Approval includes reviewer identity and
timestamp. The agent cannot self-approve.

Demonstrates:
- Workflow suspension with pending state (mocked checkpoint)
- Resumable state with approve/reject/timeout/amend paths
- Approval includes reviewer identity and timestamp
- Agent cannot self-approve
- Idempotent resume behavior (no duplicate refunds)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from adk_patterns.config import Config
from adk_patterns.contracts import (
    ExecutionStatus,
    PatternRunResult,
    ToolInvocationRecord,
)
from adk_patterns.mocks.approval_service import (
    ApprovalVerdict,
    MockApprovalService,
    ApprovalRequest,
)
from adk_patterns.models import (
    ModelResponse,
    ScriptedModel,
    ToolCallRequest,
    TokenUsage,
    text_response,
    tool_call_response,
)
from adk_patterns.shared import RunContext, run_scope

# ---------------------------------------------------------------------------
# Typed contracts
# ---------------------------------------------------------------------------


class RefundProposal(BaseModel):
    """A refund proposal submitted by an agent."""

    amount: float = Field(..., gt=0, description="Refund amount in dollars")
    reason: str = Field(..., description="Reason for the refund")
    customer_id: str = Field(..., description="Customer identifier")
    proposed_by: str = Field(default="agent", description="Who proposed the refund")


class ApprovalDecision(BaseModel):
    """An approval decision made by a human reviewer."""

    verdict: str = Field(..., description="approved, rejected, timed_out, or amended")
    reviewer: str = Field(..., description="Identity of the reviewer")
    timestamp: str = Field(..., description="ISO 8601 timestamp of the decision")
    note: str | None = Field(default=None, description="Optional reviewer note")


class RefundResult(BaseModel):
    """The result of a refund execution attempt."""

    success: bool
    refund_id: str | None = Field(default=None, description="Transaction reference")
    error: str | None = Field(default=None, description="Error message if failed")


# ---------------------------------------------------------------------------
# Helper: multiple tool calls in a single model response
# ---------------------------------------------------------------------------


def multi_tool_call_response(tool_calls: list[tuple[str, dict[str, Any]]]) -> ModelResponse:
    """Create a response with multiple tool calls.

    Args:
        tool_calls: List of (tool_name, arguments) tuples.

    Returns:
        A ModelResponse with all tool calls set.
    """
    requests = []
    for i, (name, args) in enumerate(tool_calls):
        requests.append(ToolCallRequest(id=f"call_{i:03d}", name=name, arguments=args))
    return ModelResponse(
        tool_calls=requests,
        usage=TokenUsage(prompt_tokens=100, completion_tokens=len(tool_calls) * 20, total_tokens=100 + len(tool_calls) * 20),
    )


PROPOSAL_ARGS_150 = dict(amount=150.00, reason="Product arrived damaged", customer_id="CUST-042")
PROPOSAL_ARGS_100 = dict(amount=100.00, reason="Customer dissatisfied", customer_id="CUST-007")
PROPOSAL_ARGS_200 = dict(amount=200.00, reason="Wrong item shipped", customer_id="CUST-042")

# ---------------------------------------------------------------------------
# Fixtures / sequences — all fit within max_model_calls=2
#
# Strategy: submit_refund_proposal detects auto-approve/reject/timeout and
# handles the full lifecycle inline when possible. The second model call
# produces the final text answer.
# ---------------------------------------------------------------------------

SEQUENCES: dict[str, list] = {
    # --- Approval required: agent proposes, workflow suspends -----------------
    # Call 1: submit → pending. Call 2: text answer.
    "approval_required": [
        tool_call_response("submit_refund_proposal", PROPOSAL_ARGS_150),
        text_response(
            "Refund of $150.00 for customer CUST-042 has been submitted for approval. "
            "The workflow is now pending human review."
        ),
    ],
    # --- Approved: submit auto-approves, agent reports result -----------------
    # Call 1: submit → auto-approved & auto-executed. Call 2: text answer.
    "approved": [
        tool_call_response("submit_refund_proposal", PROPOSAL_ARGS_150),
        text_response(
            "Refund of $150.00 for customer CUST-042 has been approved and executed. "
            "Refund ID: rfnd_001."
        ),
    ],
    # --- Rejected: submit auto-rejects, agent reports result -----------------
    # Call 1: submit → auto-rejected. Call 2: text answer.
    "rejected": [
        tool_call_response("submit_refund_proposal", PROPOSAL_ARGS_150),
        text_response(
            "The refund proposal for customer CUST-042 (amount $150.00) has been REJECTED "
            "by reviewer 'auto-rejecter'. The refund will not be executed."
        ),
    ],
    # --- Timeout: submit auto-timeouts, agent escalates ----------------------
    # Call 1: submit → timed out. Call 2: text answer.
    "timeout": [
        tool_call_response("submit_refund_proposal", PROPOSAL_ARGS_150),
        text_response(
            "The refund proposal for customer CUST-042 (amount $150.00) has TIMED OUT. "
            "Escalating to supervisor for manual handling."
        ),
    ],
    # --- Self-approve attempt blocked -----------------------------------------
    # Call 1: submit → pending. Call 2: text answer (agent acknowledges block).
    "self_approve": [
        tool_call_response("submit_refund_proposal", PROPOSAL_ARGS_100),
        text_response(
            "Self-approval is not permitted. The proposal for customer CUST-007 "
            "remains pending and requires a human reviewer."
        ),
    ],
    # --- Idempotent resume: execute an already-processed refund ---------------
    # Call 1: submit → auto-approved & auto-executed (detects already done).
    # Call 2: text answer.
    "idempotent_resume": [
        tool_call_response("submit_refund_proposal", PROPOSAL_ARGS_200),
        text_response(
            "Refund of $200.00 for customer CUST-042 was already processed. "
            "No duplicate refund issued."
        ),
    ],
}

QUERIES: dict[str, str] = {
    "approval_required": "Process a refund of $150 for customer CUST-042 for a damaged product.",
    "approved": "Process a refund of $150 for customer CUST-042 for a damaged product.",
    "rejected": "Process a refund of $150 for customer CUST-042 for a damaged product.",
    "timeout": "Process a refund of $150 for customer CUST-042 for a damaged product.",
    "self_approve": "I need to approve my own refund proposal for customer CUST-007.",
    "idempotent_resume": "Resume the refund workflow for proposal prop_003.",
}

# ---------------------------------------------------------------------------
# Shared mock approval service
# ---------------------------------------------------------------------------

_approval_service = MockApprovalService()
_next_proposal_id: int = 0
_executed_refunds: set[str] = set()


def _reset_service() -> None:
    """Reset the approval service to a clean state for each test run."""
    global _next_proposal_id
    _approval_service.reset()
    _next_proposal_id = 0
    _executed_refunds.clear()


def _next_proposal_id_str() -> str:
    global _next_proposal_id
    _next_proposal_id += 1
    return f"prop_{_next_proposal_id:03d}"


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def submit_refund_proposal(amount: float, reason: str, customer_id: str) -> dict[str, Any]:
    """Submit a refund proposal for human approval.

    If the approval service auto-approves or auto-rejects (mock mode),
    the decision happens immediately.  If auto-approved the refund is
    also auto-executed — an inline convenience that keeps the workflow
    within a single model call in test scenarios.

    Args:
        amount: The refund amount in dollars (must be > 0).
        reason: The reason for the refund.
        customer_id: The customer identifier.

    Returns:
        A dict with proposal_id, amount, reason, customer_id, approval_status,
        and optionally refund_id / error.
    """
    proposal_id = _next_proposal_id_str()

    # Submit to the approval service
    approval_request = ApprovalRequest(
        request_id=proposal_id,
        action="refund",
        resource=f"refund:{customer_id}",
        proposed_by="agent",
        details={
            "amount": amount,
            "reason": reason,
            "customer_id": customer_id,
        },
    )
    result = _approval_service.submit(approval_request)

    response: dict[str, Any] = {
        "proposal_id": proposal_id,
        "amount": amount,
        "reason": reason,
        "customer_id": customer_id,
        "approval_status": result.verdict.value,
        "reviewer": result.reviewer,
    }

    # Auto-execute if approved (inline convenience for test scenarios)
    if result.verdict == ApprovalVerdict.APPROVED:
        exec_result = _do_execute_refund(proposal_id)
        response["refund_id"] = exec_result.get("refund_id")
        response["refund_auto_executed"] = True
    elif result.verdict == ApprovalVerdict.REJECTED:
        response["rejection_reviewer"] = result.reviewer
    elif result.verdict == ApprovalVerdict.TIMED_OUT:
        response["timeout"] = True

    return response


def _do_execute_refund(proposal_id: str) -> dict[str, Any]:
    """Internal refund execution with idempotency check.

    Returns a dict with success / refund_id / optional error / note.
    """
    if proposal_id in _executed_refunds:
        return {
            "success": True,
            "refund_id": f"{proposal_id}_existing",
            "note": "Already processed — no duplicate refund issued.",
        }

    req = _approval_service.get(proposal_id)
    if req is None:
        return {"success": False, "error": f"Proposal {proposal_id} not found"}

    if req.verdict != ApprovalVerdict.APPROVED:
        return {
            "success": False,
            "error": f"Cannot execute: proposal status is '{req.verdict.value}', must be 'approved'",
        }

    _executed_refunds.add(proposal_id)
    refund_id = f"rfnd_{proposal_id.replace('prop_', '')}"
    return {"success": True, "refund_id": refund_id}


def check_approval_status(proposal_id: str) -> dict[str, Any]:
    """Check the current approval status of a refund proposal.

    Args:
        proposal_id: The proposal identifier to check.

    Returns:
        A dict with proposal_id, approval_status, reviewer (if any), and timestamp.
    """
    req = _approval_service.get(proposal_id)
    if req is None:
        return {
            "proposal_id": proposal_id,
            "approval_status": "not_found",
            "error": f"Proposal {proposal_id} not found",
        }

    return {
        "proposal_id": proposal_id,
        "approval_status": req.verdict.value,
        "reviewer": req.reviewer if req.reviewer else "none",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": req.reviewer_note,
    }


def execute_refund(proposal_id: str) -> dict[str, Any]:
    """Execute an approved refund.

    Only proceeds if the proposal is in 'approved' status.
    Idempotent: if the refund was already executed, returns the existing result.

    Args:
        proposal_id: The approved proposal identifier.

    Returns:
        A dict with success, refund_id, and optional error.
    """
    return _do_execute_refund(proposal_id)


def approve_refund(proposal_id: str, reviewer: str, note: str = "") -> dict[str, Any]:
    """Approve a refund proposal (intended for human reviewers only).

    Args:
        proposal_id: The proposal to approve.
        reviewer: Identity of the reviewer. Cannot be 'agent'.
        note: Optional approval note.

    Returns:
        A dict with the result of the approval attempt.
    """
    if reviewer == "agent":
        return {
            "success": False,
            "error": "Agent cannot self-approve. Only human reviewers may approve proposals.",
            "proposal_id": proposal_id,
            "reviewer": reviewer,
        }

    try:
        req = _approval_service.approve(proposal_id, reviewer, note)
        return {
            "success": True,
            "proposal_id": proposal_id,
            "reviewer": reviewer,
            "status": req.verdict.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except ValueError as e:
        return {"success": False, "error": str(e), "proposal_id": proposal_id}


def reject_refund(proposal_id: str, reviewer: str, note: str = "") -> dict[str, Any]:
    """Reject a refund proposal (intended for human reviewers only).

    Args:
        proposal_id: The proposal to reject.
        reviewer: Identity of the reviewer.
        note: Optional rejection reason.

    Returns:
        A dict with the result of the rejection.
    """
    if reviewer == "agent":
        return {
            "success": False,
            "error": "Agent cannot self-approve. Only human reviewers may reject proposals.",
            "proposal_id": proposal_id,
            "reviewer": reviewer,
        }

    try:
        req = _approval_service.reject(proposal_id, reviewer, note)
        return {
            "success": True,
            "proposal_id": proposal_id,
            "reviewer": reviewer,
            "status": req.verdict.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except ValueError as e:
        return {"success": False, "error": str(e), "proposal_id": proposal_id}


# -- Tool registry -----------------------------------------------------------

TOOL_REGISTRY: dict[str, Any] = {
    "submit_refund_proposal": submit_refund_proposal,
    "check_approval_status": check_approval_status,
    "execute_refund": execute_refund,
    "approve_refund": approve_refund,
    "reject_refund": reject_refund,
}


def _tool_definitions() -> list[dict[str, Any]]:
    """Return tool definitions in an ADK-compatible format."""
    return [
        {
            "name": "submit_refund_proposal",
            "description": "Submit a refund proposal for human approval. Amount must be > 0.",
            "parameters": {
                "amount": {"type": "number", "description": "Refund amount in dollars"},
                "reason": {"type": "string", "description": "Reason for the refund"},
                "customer_id": {"type": "string", "description": "Customer identifier"},
            },
        },
        {
            "name": "check_approval_status",
            "description": "Check the current approval status of a refund proposal.",
            "parameters": {
                "proposal_id": {"type": "string", "description": "Proposal identifier"},
            },
        },
        {
            "name": "execute_refund",
            "description": "Execute an approved refund. Idempotent — safe to call multiple times.",
            "parameters": {
                "proposal_id": {"type": "string", "description": "Approved proposal identifier"},
            },
        },
        {
            "name": "approve_refund",
            "description": "Approve a refund proposal (human reviewers only). Agent cannot self-approve.",
            "parameters": {
                "proposal_id": {"type": "string", "description": "Proposal to approve"},
                "reviewer": {"type": "string", "description": "Reviewer identity"},
                "note": {"type": "string", "description": "Optional approval note"},
            },
        },
        {
            "name": "reject_refund",
            "description": "Reject a refund proposal (human reviewers only).",
            "parameters": {
                "proposal_id": {"type": "string", "description": "Proposal to reject"},
                "reviewer": {"type": "string", "description": "Reviewer identity"},
                "note": {"type": "string", "description": "Optional rejection reason"},
            },
        },
    ]


# ---------------------------------------------------------------------------
# Core orchestration
# ---------------------------------------------------------------------------


def _validate_and_execute(tool_name: str, arguments: dict[str, Any]) -> Any:
    """Execute a tool with runtime type validation.

    Raises:
        ValueError: If the tool is unknown.
        TypeError: If any argument has the wrong type.
    """
    if tool_name not in TOOL_REGISTRY:
        msg = f"Tool '{tool_name}' is not available. Available tools: {', '.join(sorted(TOOL_REGISTRY))}"
        raise ValueError(msg)

    fn = TOOL_REGISTRY[tool_name]

    import inspect
    import typing

    sig = inspect.signature(fn)
    try:
        hints = typing.get_type_hints(fn)
    except Exception:
        hints = {}
    for param_name, param in sig.parameters.items():
        if param_name in arguments:
            actual_value = arguments[param_name]
            expected_type = hints.get(param_name, param.annotation)
            if expected_type is str and not isinstance(actual_value, str):
                raise TypeError(
                    f"Argument '{param_name}' must be str, "
                    f"got {type(actual_value).__name__} ({actual_value!r})"
                )
            if expected_type is float and not isinstance(actual_value, (int, float)):
                raise TypeError(
                    f"Argument '{param_name}' must be a number, "
                    f"got {type(actual_value).__name__} ({actual_value!r})"
                )

    return fn(**arguments)


def _execute_tool_calls(
    ctx: RunContext,
    tool_calls: list,
) -> dict[str, Any]:
    """Execute a batch of tool calls and record results.

    Returns a dict mapping tool names to their results or error info.
    """
    results: dict[str, Any] = {}

    for tc in tool_calls:
        ctx.audit("agent", "tool_call", resource=tc.name, metadata={"call_id": tc.id})
        try:
            result = _validate_and_execute(tc.name, tc.arguments)
            ctx.record_tool_call(
                ToolInvocationRecord(
                    tool_name=tc.name,
                    validated_arguments=dict(tc.arguments),
                    result_summary={"status": "success"},
                )
            )
            results[tc.name] = result
        except (ValueError, TypeError, Exception) as e:
            error_type = type(e).__name__
            ctx.record_tool_call(
                ToolInvocationRecord(
                    tool_name=tc.name,
                    validated_arguments=dict(tc.arguments),
                    error_type=error_type,
                )
            )
            ctx.audit("agent", "tool_error", resource=tc.name, outcome="failure", metadata={"error": str(e)})
            results[tc.name] = {"error": str(e), "error_type": error_type}

    return results


def run_approval_agent(
    ctx: RunContext,
    model: ScriptedModel,
    query: str,
) -> dict[str, Any]:
    """Run the human-approval-gate agent loop.

    Args:
        ctx: Run context for audit and budget tracking.
        model: ScriptedModel with pre-configured response sequence.
        query: The user's request text.

    Returns:
        A dict with keys 'tool_results', 'final_answer', and state tracking keys
        (proposal, approval_status, refund_result).
    """
    state: dict[str, Any] = {
        "tool_results": {},
        "final_answer": "",
        "proposal": None,
        "approval_status": None,
        "refund_result": None,
    }
    messages: list[dict[str, Any]] = [{"role": "user", "content": query}]

    system_prompt = (
        "You are a refund processing assistant. You handle refund proposals that require "
        "human approval before execution.\n\n"
        "Workflow:\n"
        "1. CALL submit_refund_proposal(amount, reason, customer_id) to create a refund proposal.\n"
        "2. The proposal enters 'pending' status and waits for human approval.\n"
        "3. CALL check_approval_status(proposal_id) to check if a human has reviewed it.\n"
        "4. If approved, CALL execute_refund(proposal_id) to process the refund.\n"
        "5. If rejected, inform the user that the refund was denied.\n"
        "6. If timed out, escalate to a supervisor.\n\n"
        "IMPORTANT: You CANNOT self-approve. Only human reviewers may use approve_refund.\n"
        "Call one tool at a time and wait for the result before calling another.\n"
        "When you have all the information you need, provide the final answer."
    )

    for iteration in range(3):  # bounded iteration budget
        ctx.record_iteration()

        budget_status = ctx.check_budget()
        if budget_status:
            ctx.mark_budget_exhausted()
            break

        response = model.invoke(
            system_instruction=system_prompt,
            messages=messages,
            tools=_tool_definitions(),
        )
        ctx.record_model_call(tokens=response.usage.total_tokens)
        ctx.audit("agent", "model_call", resource=f"iteration_{iteration}")

        # Check if response has tool calls
        if response.tool_calls:
            tool_results = _execute_tool_calls(ctx, response.tool_calls)
            state["tool_results"].update(tool_results)

            # Extract state from tool results
            for tool_name, result in tool_results.items():
                if "error" not in result:
                    if tool_name == "submit_refund_proposal" and state["proposal"] is None:
                        state["proposal"] = {
                            "proposal_id": result.get("proposal_id"),
                            "amount": result.get("amount"),
                            "reason": result.get("reason"),
                            "customer_id": result.get("customer_id"),
                            "approval_status": result.get("approval_status", "pending"),
                        }
                        state["approval_status"] = result.get("approval_status", "pending")
                        # If auto-executed inline, also set refund_result
                        if result.get("refund_auto_executed"):
                            state["refund_result"] = {
                                "success": True,
                                "refund_id": result.get("refund_id"),
                            }
                    elif tool_name == "check_approval_status":
                        state["approval_status"] = result.get("approval_status", state.get("approval_status"))
                    elif tool_name == "execute_refund":
                        state["refund_result"] = {
                            "success": result.get("success"),
                            "refund_id": result.get("refund_id"),
                            "error": result.get("error"),
                        }

            # Feed results back to model
            result_lines = []
            for tool_name, result in tool_results.items():
                if "error" in result:
                    result_lines.append(f"Tool {tool_name} returned error: {result['error']}")
                else:
                    result_lines.append(f"Tool {tool_name} returned: {result}")
            messages.append({"role": "user", "content": "\n".join(result_lines)})
        else:
            # Model produced a text response — this is the final answer
            state["final_answer"] = response.text
            ctx.audit("agent", "final_answer", outcome="success", metadata={"answer": response.text})
            break

    ctx.snapshot_state(state)
    return state


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def run(config: Config | None = None, scenario: str = "default") -> PatternRunResult:
    """Entry point for CLI and tests.

    Args:
        config: Application configuration (uses defaults if None).
        scenario: Test scenario key.

    Returns:
        A PatternRunResult with status, output, metrics, and audit trail.
    """
    model = ScriptedModel()

    seq = SEQUENCES.get(scenario)
    if seq:
        model.set_response_sequence(seq)

    query = QUERIES.get(scenario, "Process a refund of $150 for customer CUST-042 for a damaged product.")

    # Configure approval service based on scenario
    _reset_service()
    if scenario == "approved":
        _approval_service.set_auto_approve()
    elif scenario == "rejected":
        _approval_service.set_auto_reject()
    elif scenario == "timeout":
        _approval_service.set_timeout()
    elif scenario == "idempotent_resume":
        _approval_service.set_auto_approve()
        # Pre-execute to demonstrate idempotent behavior
        _executed_refunds.add("prop_003")

    with run_scope("human-approval-gate", scenario, max_model_calls=2, max_tool_calls=5) as ctx:
        state = run_approval_agent(ctx, model, query)
        ctx.output = state

    return ctx.to_result()


def main(config: Config | None = None, scenario: str = "default") -> PatternRunResult:
    """Standard entry point called by CLI."""
    return run(config=config, scenario=scenario)
