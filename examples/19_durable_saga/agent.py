"""Pattern 19: Durable SAGA.

Scenario: Mocked travel booking workflow with append-only event log,
checkpointing, idempotency, crash recovery, and compensating rollback.

Workflow steps:
  1. Reserve flight
  2. Reserve hotel
  3. Charge payment
  4. Issue confirmation

On failure: compensating actions in reverse order.
On compensation failure: human escalation.

Uses a local FakeDurableRunner (event-sourced) — no real workflow engine.
Demonstrates how to replace with Temporal or persistent ADK session service.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from typing import Any

from adk_patterns.config import Config
from adk_patterns.contracts import ExecutionStatus, PatternRunResult, ToolInvocationRecord
from adk_patterns.mocks.event_log import EventLog, LogEntry
from adk_patterns.mocks.payment_service import MockPaymentService
from adk_patterns.models import ScriptedModel
from adk_patterns.shared import RunContext, run_scope

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAGA_STEPS = ["reserve_flight", "reserve_hotel", "charge_payment", "issue_confirmation"]

COMPENSATION_ACTIONS = {
    "issue_confirmation": "cancel_confirmation",
    "charge_payment": "refund_payment",
    "reserve_hotel": "release_hotel",
    "reserve_flight": "release_flight",
}

COMPENSATION_DISPLAY = {
    "cancel_confirmation": "Cancelling ticket confirmation",
    "refund_payment": "Refunding payment",
    "release_hotel": "Releasing hotel reservation",
    "release_flight": "Releasing flight reservation",
}

# ---------------------------------------------------------------------------
# State keys
# ---------------------------------------------------------------------------
# event_log[], checkpoints{}, saga_status, compensation_log[]

# ---------------------------------------------------------------------------
# In-memory booking state (mocked external services)
# ---------------------------------------------------------------------------

_booking_db: dict[str, dict[str, Any]] = {}
_reserved_flights: set[str] = set()
_reserved_hotels: set[str] = set()
_confirmed_tickets: set[str] = set()
_compensation_log: list[dict[str, Any]] = []
_saga_id_counter: int = 0


def _reset_booking_state() -> None:
    """Reset all mock booking state for a fresh test."""
    global _saga_id_counter
    _booking_db.clear()
    _reserved_flights.clear()
    _reserved_hotels.clear()
    _confirmed_tickets.clear()
    _compensation_log.clear()
    _saga_id_counter = 0


def _next_saga_id() -> str:
    global _saga_id_counter
    _saga_id_counter += 1
    return f"saga_{_saga_id_counter:03d}"


# ---------------------------------------------------------------------------
# Payment service (shared mock)
# ---------------------------------------------------------------------------

_payment_service = MockPaymentService()


def _reset_payment_service() -> None:
    _payment_service.reset()


# ---------------------------------------------------------------------------
# Event log (append-only)
# ---------------------------------------------------------------------------

_event_log = EventLog()


def _reset_event_log() -> None:
    _event_log.clear()


# ---------------------------------------------------------------------------
# Booking tool functions (idempotent side-effect operations)
# ---------------------------------------------------------------------------


def reserve_flight(
    booking_id: str,
    flight: str,
    customer: str,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Reserve a flight. Idempotent — safe to replay."""
    if idempotency_key and idempotency_key in _reserved_flights:
        return {
            "success": True,
            "booking_id": booking_id,
            "flight": flight,
            "customer": customer,
            "note": "Already reserved — no duplicate side effect.",
        }
    _reserved_flights.add(idempotency_key or booking_id)
    _booking_db[booking_id] = {
        "step": "reserve_flight",
        "booking_id": booking_id,
        "flight": flight,
        "customer": customer,
        "status": "reserved",
    }
    return {
        "success": True,
        "booking_id": booking_id,
        "flight": flight,
        "customer": customer,
        "status": "reserved",
    }


def reserve_hotel(
    booking_id: str,
    hotel: str,
    customer: str,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Reserve a hotel room. Idempotent."""
    if idempotency_key and idempotency_key in _reserved_hotels:
        return {
            "success": True,
            "booking_id": booking_id,
            "hotel": hotel,
            "customer": customer,
            "note": "Already reserved — no duplicate side effect.",
        }
    _reserved_hotels.add(idempotency_key or booking_id)
    _booking_db.setdefault(booking_id, {})["step"] = "reserve_hotel"
    _booking_db[booking_id].update(
        {
            "hotel": hotel,
            "customer": customer,
            "status": "reserved",
        }
    )
    return {
        "success": True,
        "booking_id": booking_id,
        "hotel": hotel,
        "customer": customer,
        "status": "reserved",
    }


def charge_payment(
    booking_id: str,
    amount: float,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Charge the payment. Uses MockPaymentService. Idempotent via idempotency key."""
    try:
        payment = _payment_service.authorize(
            payment_id=f"pay_{booking_id}",
            amount=amount,
            idempotency_key=idempotency_key,
        )
        captured = _payment_service.capture(payment.payment_id)
        _booking_db.setdefault(booking_id, {}).update(
            {
                "step": "charge_payment",
                "payment_id": captured.payment_id,
                "amount": amount,
                "status": "charged",
            }
        )
        return {
            "success": True,
            "booking_id": booking_id,
            "payment_id": captured.payment_id,
            "amount": amount,
            "status": "charged",
        }
    except Exception as e:
        return {"success": False, "booking_id": booking_id, "error": str(e)}


def issue_confirmation(
    booking_id: str,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Issue a ticket confirmation. Idempotent."""
    if idempotency_key and idempotency_key in _confirmed_tickets:
        return {
            "success": True,
            "booking_id": booking_id,
            "confirmation_id": f"cnf_{booking_id}",
            "note": "Already confirmed — no duplicate side effect.",
        }
    _confirmed_tickets.add(idempotency_key or booking_id)
    conf_id = f"cnf_{booking_id}"
    _booking_db.setdefault(booking_id, {}).update(
        {
            "step": "issue_confirmation",
            "confirmation_id": conf_id,
            "status": "confirmed",
        }
    )
    return {
        "success": True,
        "booking_id": booking_id,
        "confirmation_id": conf_id,
        "status": "confirmed",
    }


# ---------------------------------------------------------------------------
# Compensation actions (reverse-order rollback)
# ---------------------------------------------------------------------------


def cancel_confirmation(booking_id: str) -> dict[str, Any]:
    """Cancel a ticket confirmation."""
    if booking_id in _confirmed_tickets:
        _confirmed_tickets.discard(booking_id)
    if booking_id in _booking_db:
        _booking_db[booking_id]["status"] = "confirmation_cancelled"
    return {"success": True, "booking_id": booking_id, "action": "cancel_confirmation"}


def refund_payment(booking_id: str) -> dict[str, Any]:
    """Refund a charged payment."""
    try:
        payment = _payment_service.get_payment(f"pay_{booking_id}")
        if payment:
            _payment_service.refund(payment.payment_id)
        return {"success": True, "booking_id": booking_id, "action": "refund_payment"}
    except Exception as e:
        return {"success": False, "booking_id": booking_id, "action": "refund_payment", "error": str(e)}


def release_hotel(booking_id: str) -> dict[str, Any]:
    """Release a hotel reservation."""
    ik = f"hotel_{booking_id}"
    _reserved_hotels.discard(ik)
    if booking_id in _booking_db:
        _booking_db[booking_id]["status"] = "hotel_released"
    return {"success": True, "booking_id": booking_id, "action": "release_hotel"}


def release_flight(booking_id: str) -> dict[str, Any]:
    """Release a flight reservation."""
    ik = f"flight_{booking_id}"
    _reserved_flights.discard(ik)
    if booking_id in _booking_db:
        _booking_db[booking_id]["status"] = "flight_released"
    return {"success": True, "booking_id": booking_id, "action": "release_flight"}


# ---------------------------------------------------------------------------
# Compensation function registry
# ---------------------------------------------------------------------------

COMPENSATION_REGISTRY: dict[str, Any] = {
    "cancel_confirmation": cancel_confirmation,
    "refund_payment": refund_payment,
    "release_hotel": release_hotel,
    "release_flight": release_flight,
}

TOOL_REGISTRY: dict[str, Any] = {
    "reserve_flight": reserve_flight,
    "reserve_hotel": reserve_hotel,
    "charge_payment": charge_payment,
    "issue_confirmation": issue_confirmation,
    "cancel_confirmation": cancel_confirmation,
    "refund_payment": refund_payment,
    "release_hotel": release_hotel,
    "release_flight": release_flight,
}


def _tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "reserve_flight",
            "description": "Reserve a flight for a customer. Idempotent.",
            "parameters": {
                "booking_id": {"type": "string", "description": "Booking identifier"},
                "flight": {"type": "string", "description": "Flight number"},
                "customer": {"type": "string", "description": "Customer identifier"},
                "idempotency_key": {
                    "type": "string",
                    "description": "Idempotency key for safe replay",
                },
            },
        },
        {
            "name": "reserve_hotel",
            "description": "Reserve a hotel room. Idempotent.",
            "parameters": {
                "booking_id": {"type": "string", "description": "Booking identifier"},
                "hotel": {"type": "string", "description": "Hotel name"},
                "customer": {"type": "string", "description": "Customer identifier"},
                "idempotency_key": {
                    "type": "string",
                    "description": "Idempotency key for safe replay",
                },
            },
        },
        {
            "name": "charge_payment",
            "description": "Charge the customer's payment. Idempotent.",
            "parameters": {
                "booking_id": {"type": "string", "description": "Booking identifier"},
                "amount": {"type": "number", "description": "Payment amount"},
                "idempotency_key": {
                    "type": "string",
                    "description": "Idempotency key for safe replay",
                },
            },
        },
        {
            "name": "issue_confirmation",
            "description": "Issue a ticket confirmation. Idempotent.",
            "parameters": {
                "booking_id": {"type": "string", "description": "Booking identifier"},
                "idempotency_key": {
                    "type": "string",
                    "description": "Idempotency key for safe replay",
                },
            },
        },
        {
            "name": "cancel_confirmation",
            "description": "Cancel a ticket confirmation (compensation).",
            "parameters": {
                "booking_id": {"type": "string", "description": "Booking identifier"},
            },
        },
        {
            "name": "refund_payment",
            "description": "Refund a charged payment (compensation).",
            "parameters": {
                "booking_id": {"type": "string", "description": "Booking identifier"},
            },
        },
        {
            "name": "release_hotel",
            "description": "Release a hotel reservation (compensation).",
            "parameters": {
                "booking_id": {"type": "string", "description": "Booking identifier"},
            },
        },
        {
            "name": "release_flight",
            "description": "Release a flight reservation (compensation).",
            "parameters": {
                "booking_id": {"type": "string", "description": "Booking identifier"},
            },
        },
    ]


# ---------------------------------------------------------------------------
# FakeDurableRunner — event-sourced SAGA executor
# ---------------------------------------------------------------------------


class FakeDurableRunner:
    """Event-sourced SAGA runner with checkpointing, resume, and compensation.

    No real workflow engine — this is a local implementation that demonstrates
    the durable execution pattern. Uses EventLog for append-only event recording
    and in-memory checkpoints for crash recovery.

    To replace with Temporal:
      - Replace this class with a Temporal workflow
      - Each step becomes an Activity
      - Checkpoints are Temporal's built-in workflow state
      - Saga compensations use Temporal's native compensation API

    To replace with persistent ADK session service:
      - Checkpoints go into ADK session state instead of dict
      - Event log persists to a DB table instead of in-memory list
      - Runner uses ADK's before/after model callbacks for checkpointing
    """

    def __init__(self, event_log: EventLog | None = None) -> None:
        self.event_log = event_log or EventLog()
        self.checkpoints: dict[str, dict[str, Any]] = {}
        self.saga_status: str = "pending"
        self.compensation_log: list[dict[str, Any]] = []

    def snapshot_state(self) -> dict[str, Any]:
        """Return full state snapshot for persistence / checkpointing."""
        return {
            "event_log": [e.__dict__ for e in self.event_log.get_all()],
            "checkpoints": self.checkpoints,
            "saga_status": self.saga_status,
            "compensation_log": list(self.compensation_log),
        }

    def log_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Append an immutable event to the log."""
        entry = LogEntry(
            entry_id=uuid.uuid4().hex[:12],
            event_type=event_type,
            data=data,
        )
        self.event_log.append(entry)

    def checkpoint(self, step_name: str, result: dict[str, Any]) -> None:
        """Save a checkpoint after completing a step."""
        self.checkpoints[step_name] = {
            "result": result,
            "status": "completed",
        }
        self.log_event(f"checkpoint.{step_name}", {"step": step_name, "result": result})

    def is_step_completed(self, step_name: str) -> bool:
        """Check whether a step has already been checkpointed (for resume)."""
        cp = self.checkpoints.get(step_name, {})
        return cp.get("status") == "completed"

    def get_completed_steps(self) -> list[str]:
        """Return list of steps completed so far, in order."""
        return [s for s in SAGA_STEPS if self.is_step_completed(s)]

    def execute_step(self, step_name: str, tool_func: Any, args: dict[str, Any]) -> dict[str, Any]:
        """Execute a single step with idempotency and checkpointing.

        If the step is already checkpointed, skip execution (resume path).
        """
        if self.is_step_completed(step_name):
            return {"success": True, "step": step_name, "skipped": True}

        # Inject idempotency key if not provided
        if "idempotency_key" not in args or args["idempotency_key"] is None:
            args["idempotency_key"] = f"{step_name}_{args.get('booking_id', 'unknown')}"

        self.log_event(f"step.{step_name}.start", {"step": step_name, "args": args})
        result = tool_func(**args)

        if result.get("success"):
            self.checkpoint(step_name, result)
            self.log_event(f"step.{step_name}.success", {"step": step_name, "result": result})
        else:
            self.log_event(f"step.{step_name}.failure", {"step": step_name, "error": result.get("error")})

        return result

    def compensate(self, booking_id: str, failed_step: str | None = None) -> dict[str, Any]:
        """Run compensating actions in reverse order.

        Only compensates steps that completed before 'failed_step'.
        Handles compensation failures by logging and escalating to human.

        Returns a dict with compensation results and any escalation info.
        """
        completed = self.get_completed_steps()
        if failed_step and failed_step in completed:
            # Only compensate steps before the failed one
            idx = completed.index(failed_step)
            to_compensate = list(reversed(completed[:idx]))
        else:
            to_compensate = list(reversed(completed))

        self.saga_status = "compensating"
        self.log_event("compensation.start", {"steps": to_compensate})

        compensation_results: list[dict[str, Any]] = []
        escalation_required = False
        escalation_reasons: list[str] = []

        for step in to_compensate:
            compensate_action = COMPENSATION_ACTIONS.get(step)
            if compensate_action and compensate_action in COMPENSATION_REGISTRY:
                func = COMPENSATION_REGISTRY[compensate_action]
                try:
                    result = func(booking_id=booking_id)
                    compensation_results.append(
                        {"step": step, "action": compensate_action, "result": result}
                    )
                    self.compensation_log.append(
                        {"step": step, "action": compensate_action, "success": result.get("success", False)}
                    )
                    self.log_event(
                        f"compensation.{compensate_action}",
                        {"step": step, "success": result.get("success", False)},
                    )
                    if not result.get("success"):
                        escalation_required = True
                        escalation_reasons.append(
                            f"Compensation {compensate_action} for {step} failed: {result.get('error', 'unknown')}"
                        )
                except Exception as e:
                    compensation_results.append(
                        {"step": step, "action": compensate_action, "error": str(e)}
                    )
                    self.compensation_log.append(
                        {"step": step, "action": compensate_action, "success": False}
                    )
                    escalation_required = True
                    escalation_reasons.append(
                        f"Compensation {compensate_action} for {step} raised exception: {e}"
                    )
            else:
                # Step has no compensating action defined
                compensation_results.append(
                    {"step": step, "action": "noop", "note": "No compensation defined"}
                )

        self.log_event("compensation.result", {"results": compensation_results})

        if escalation_required:
            self.saga_status = "escalated"
            escalation_result = {
                "compensation_results": compensation_results,
                "escalation_required": True,
                "escalation_message": (
                    "Human escalation required. The following compensating actions failed:\n"
                    + "\n".join(f"  - {r}" for r in escalation_reasons)
                ),
            }
            self.log_event("compensation.escalation", escalation_result)
            return escalation_result
        else:
            self.saga_status = "compensated"
            return {
                "compensation_results": compensation_results,
                "escalation_required": False,
                "escalation_message": None,
            }


# ---------------------------------------------------------------------------
# Tool argument helpers
# ---------------------------------------------------------------------------

BOOKING_ARGS = {
    "booking_id": "bk_001",
    "flight": "AA123",
    "hotel": "Hilton Downtown",
    "customer": "CUST-001",
    "amount": 599.99,
}


def _execute_tool(ctx: RunContext, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute a tool with validation and recording."""
    if tool_name not in TOOL_REGISTRY:
        msg = f"Tool '{tool_name}' is not available."
        raise ValueError(msg)

    fn = TOOL_REGISTRY[tool_name]
    ctx.audit("agent", "tool_call", resource=tool_name, metadata={"args": arguments})

    try:
        result = fn(**arguments)
        ctx.record_tool_call(
            ToolInvocationRecord(
                tool_name=tool_name,
                validated_arguments=dict(arguments),
                result_summary={"status": "success" if result.get("success") else "failed"},
            )
        )
        return result
    except Exception as e:
        error_type = type(e).__name__
        ctx.record_tool_call(
            ToolInvocationRecord(
                tool_name=tool_name,
                validated_arguments=dict(arguments),
                error_type=error_type,
            )
        )
        ctx.audit("agent", "tool_error", resource=tool_name, outcome="failure", metadata={"error": str(e)})
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Core orchestration — run_saga
# ---------------------------------------------------------------------------


def run_saga(
    ctx: RunContext,
    runner: FakeDurableRunner,
    booking_args: dict[str, Any],
    crash_after: str | None = None,
    fail_step: str | None = None,
    fail_compensation: str | None = None,
) -> dict[str, Any]:
    """Execute the SAGA workflow.

    Args:
        ctx: Run context.
        runner: FakeDurableRunner instance.
        booking_args: Dict with booking_id, flight, hotel, customer, amount.
        crash_after: If set, simulate crash after this step completes.
        fail_step: If set, make this step fail.
        fail_compensation: If set, make this compensation action fail.

    Returns:
        State dict with full saga result.
    """
    state: dict[str, Any] = {
        "event_log": [],
        "checkpoints": {},
        "saga_status": "pending",
        "compensation_log": [],
        "final_answer": "",
    }

    # Phase 1: Forward execution
    for step_name in SAGA_STEPS:
        ctx.record_iteration()
        budget_status = ctx.check_budget()
        if budget_status:
            ctx.mark_budget_exhausted()
            runner.saga_status = "budget_exhausted"
            break

        # Build step-specific args
        if step_name == "reserve_flight":
            args = {
                "booking_id": booking_args["booking_id"],
                "flight": booking_args["flight"],
                "customer": booking_args["customer"],
                "idempotency_key": f"flight_{booking_args['booking_id']}",
            }
        elif step_name == "reserve_hotel":
            args = {
                "booking_id": booking_args["booking_id"],
                "hotel": booking_args["hotel"],
                "customer": booking_args["customer"],
                "idempotency_key": f"hotel_{booking_args['booking_id']}",
            }
        elif step_name == "charge_payment":
            args = {
                "booking_id": booking_args["booking_id"],
                "amount": booking_args["amount"],
                "idempotency_key": f"payment_{booking_args['booking_id']}",
            }
        elif step_name == "issue_confirmation":
            args = {
                "booking_id": booking_args["booking_id"],
                "idempotency_key": f"confirm_{booking_args['booking_id']}",
            }
        else:
            args = {}

        runner.log_event(f"step.{step_name}.attempt", {"step": step_name})

        # Inject simulated failure
        if step_name == fail_step:
            runner.log_event(f"step.{step_name}.failed", {"step": step_name, "error": "Simulated failure"})
            runner.saga_status = "failed"
            state["failure_step"] = step_name
            # Execute compensation
            compensation_result = runner.compensate(
                booking_args["booking_id"], failed_step=step_name
            )
            state["compensation_result"] = compensation_result
            state["saga_status"] = runner.saga_status
            break

        result = runner.execute_step(step_name, TOOL_REGISTRY[step_name], args)

        if not result.get("success"):
            runner.saga_status = "failed"
            state["failure_step"] = step_name
            state["step_error"] = result.get("error", "Unknown error")
            # Execute compensation
            compensation_result = runner.compensate(
                booking_args["booking_id"], failed_step=step_name
            )
            state["compensation_result"] = compensation_result
            state["saga_status"] = runner.saga_status
            break

        # Simulate crash after specific step
        if crash_after and step_name == crash_after:
            runner.saga_status = "crashed"
            state["saga_status"] = "crashed"
            state["crash_step"] = step_name
            # We break without completing remaining steps — resume will fix this
            break

    # Phase 2: If saga completed all steps successfully
    if runner.saga_status == "pending" and len(runner.get_completed_steps()) == len(SAGA_STEPS):
        runner.saga_status = "completed"
        state["saga_status"] = "completed"
        state["final_answer"] = (
            f"Travel booking complete! Flight {booking_args['flight']} reserved, "
            f"hotel {booking_args['hotel']} reserved, "
            f"payment of ${booking_args['amount']:.2f} charged, "
            f"and confirmation issued."
        )

    # Snapshot state
    state["event_log"] = [e.__dict__ for e in runner.event_log.get_all()]
    state["checkpoints"] = dict(runner.checkpoints)
    state["compensation_log"] = list(runner.compensation_log)

    ctx.snapshot_state(state)
    return state


# ---------------------------------------------------------------------------
# Resume from checkpoint
# ---------------------------------------------------------------------------


def resume_saga(
    ctx: RunContext,
    runner: FakeDurableRunner,
    booking_args: dict[str, Any],
) -> dict[str, Any]:
    """Resume a crashed SAGA from its last checkpoint.

    Replays completed steps (skipping them via idempotency) and
    continues forward execution for incomplete steps.
    """
    state: dict[str, Any] = {
        "event_log": [e.__dict__ for e in runner.event_log.get_all()],
        "checkpoints": dict(runner.checkpoints),
        "saga_status": runner.saga_status,
        "compensation_log": list(runner.compensation_log),
        "final_answer": "",
        "resumed": True,
        "completed_steps_before_resume": runner.get_completed_steps(),
    }

    # Continue from first incomplete step
    for step_name in SAGA_STEPS:
        if runner.is_step_completed(step_name):
            continue  # Skip completed — will be a no-op via idempotency

        ctx.record_iteration()
        budget_status = ctx.check_budget()
        if budget_status:
            ctx.mark_budget_exhausted()
            runner.saga_status = "budget_exhausted"
            break

        # Build step-specific args
        if step_name == "reserve_flight":
            args = {
                "booking_id": booking_args["booking_id"],
                "flight": booking_args["flight"],
                "customer": booking_args["customer"],
                "idempotency_key": f"flight_{booking_args['booking_id']}",
            }
        elif step_name == "reserve_hotel":
            args = {
                "booking_id": booking_args["booking_id"],
                "hotel": booking_args["hotel"],
                "customer": booking_args["customer"],
                "idempotency_key": f"hotel_{booking_args['booking_id']}",
            }
        elif step_name == "charge_payment":
            args = {
                "booking_id": booking_args["booking_id"],
                "amount": booking_args["amount"],
                "idempotency_key": f"payment_{booking_args['booking_id']}",
            }
        elif step_name == "issue_confirmation":
            args = {
                "booking_id": booking_args["booking_id"],
                "idempotency_key": f"confirm_{booking_args['booking_id']}",
            }
        else:
            args = {}

        runner.log_event(f"step.{step_name}.resume_attempt", {"step": step_name})
        result = runner.execute_step(step_name, TOOL_REGISTRY[step_name], args)

        if not result.get("success"):
            runner.saga_status = "failed"
            state["failure_step"] = step_name
            compensation_result = runner.compensate(booking_args["booking_id"], failed_step=step_name)
            state["compensation_result"] = compensation_result
            state["saga_status"] = runner.saga_status
            break

    if runner.saga_status in ("pending", "crashed") and len(runner.get_completed_steps()) == len(SAGA_STEPS):
        runner.saga_status = "completed"
        state["saga_status"] = "completed"
        state["final_answer"] = (
            f"Travel booking complete after resume! Flight {booking_args['flight']} reserved, "
            f"hotel {booking_args['hotel']} reserved, "
            f"payment of ${booking_args['amount']:.2f} charged, "
            f"and confirmation issued."
        )

    # Final state snapshot
    state["event_log"] = [e.__dict__ for e in runner.event_log.get_all()]
    state["checkpoints"] = dict(runner.checkpoints)
    state["compensation_log"] = list(runner.compensation_log)

    ctx.snapshot_state(state)
    return state


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run(config: Config | None = None, scenario: str = "default") -> PatternRunResult:
    """Entry point for CLI and tests.

    Args:
        config: Application configuration (uses defaults if None).
        scenario: Test scenario key.

    Returns:
        A PatternRunResult with status, output, metrics, and audit trail.
    """
    _reset_booking_state()
    _reset_payment_service()
    _reset_event_log()

    runner = FakeDurableRunner(event_log=_event_log)
    booking_args = dict(BOOKING_ARGS)

    # Configure simulated failure based on scenario
    crash_after: str | None = None
    fail_step: str | None = None
    fail_compensation: str | None = None
    do_resume: bool = False

    if scenario == "crash_after_payment":
        crash_after = "charge_payment"
    elif scenario == "resume_no_duplicate":
        crash_after = "charge_payment"
        do_resume = True
    elif scenario == "compensation_on_failure":
        fail_step = "issue_confirmation"
    elif scenario == "compensation_failure":
        fail_step = "issue_confirmation"
        fail_compensation = "refund_payment"
    elif scenario == "idempotency":
        pass  # We'll handle idempotency by replaying events in the test

    with run_scope("durable-saga", scenario, max_model_calls=10, max_tool_calls=20) as ctx:
        if do_resume:
            # Phase 1: Run until crash
            _reset_booking_state()
            _reset_payment_service()
            _reset_event_log()
            runner = FakeDurableRunner(event_log=_event_log)
            crash_state = run_saga(ctx, runner, booking_args, crash_after=crash_after)

            # Phase 2: Resume from checkpoint (new context for clarity in tests)
            resume_runner = FakeDurableRunner(event_log=_event_log)
            # Replay existing checkpoints from the log
            for entry in _event_log.get_all():
                if entry.event_type.startswith("checkpoint."):
                    step_name = entry.event_type.split(".", 1)[1]
                    resume_runner.checkpoints[step_name] = entry.data

            state = resume_saga(ctx, resume_runner, booking_args)
        else:
            state = run_saga(
                ctx,
                runner,
                booking_args,
                crash_after=crash_after,
                fail_step=fail_step,
                fail_compensation=fail_compensation,
            )

        # Propagate saga failure/compensation status to the run result
        if state.get("saga_status") in ("failed", "compensated", "escalated"):
            reason = state.get("failure_step", state["saga_status"])
            if fail_step:
                reason = f"Saga step {fail_step} failed"
            elif state.get("failure_step"):
                reason = f"Saga step {state['failure_step']} failed"
            ctx.mark_failed(reason)

        ctx.output = state

    return ctx.to_result()


def main(config: Config | None = None, scenario: str = "default") -> PatternRunResult:
    """Standard entry point called by CLI."""
    return run(config=config, scenario=scenario)
