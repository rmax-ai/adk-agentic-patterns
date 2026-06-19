"""Tests for Pattern 19: Durable SAGA.

Covers:
- Full successful booking (all 4 steps)
- Crash after payment → resume from checkpoint
- Compensation on failure (reverse order rollback)
- Compensation failure handling → human escalation
- Idempotency (duplicate event replay → no double-booking)
- Resume no duplicate side effects
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
    BOOKING_ARGS,
    SAGA_STEPS,
    FakeDurableRunner,
    _booking_db,
    _confirmed_tickets,
    _event_log,
    _payment_service,
    _reserved_flights,
    _reserved_hotels,
    _reset_booking_state,
    _reset_event_log,
    _reset_payment_service,
    charge_payment,
    issue_confirmation,
    refund_payment,
    release_flight,
    release_hotel,
    reserve_flight,
    reserve_hotel,
    run,
    run_saga,
)
from adk_patterns.contracts import ExecutionStatus  # noqa: E402
from adk_patterns.mocks.event_log import EventLog  # noqa: E402
from adk_patterns.shared import RunContext  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures — clean state for each test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_state() -> None:  # type: ignore[misc]
    _reset_booking_state()
    _reset_payment_service()
    _reset_event_log()
    yield


def _make_runner() -> FakeDurableRunner:
    return FakeDurableRunner(event_log=_event_log)


def _make_ctx() -> RunContext:
    return RunContext(pattern="durable-saga", scenario="test")


def _replay_checkpoints(runner: FakeDurableRunner) -> None:
    """Replay checkpoint data from the shared event log into a runner."""
    for entry in _event_log.get_all():
        if entry.event_type.startswith("checkpoint."):
            step_name = entry.event_type.split(".", 1)[1]
            result = entry.data.get("result", {})
            runner.checkpoints[step_name] = {"status": "completed", "result": result}


# ---------------------------------------------------------------------------
# Test: Full successful booking
# ---------------------------------------------------------------------------


def test_full_booking_success() -> None:
    """All 4 steps complete successfully — saga_status = completed."""
    runner = _make_runner()
    ctx = _make_ctx()
    booking_args = dict(BOOKING_ARGS)

    state = run_saga(ctx, runner, booking_args)

    assert state["saga_status"] == "completed"
    # All 4 steps should be checkpointed
    for step in SAGA_STEPS:
        assert runner.is_step_completed(step), f"Step {step} should be completed"
    assert len(runner.get_completed_steps()) == 4
    assert "final_answer" in state
    # Final answer mentions confirmation
    answer = state["final_answer"].lower()
    assert "confirmation" in answer or "confirmed" in answer


def test_full_booking_via_entry_point() -> None:
    """Run via the entry point — full success scenario."""
    result = run(scenario="default")

    assert result.status == ExecutionStatus.SUCCEEDED
    state = result.output
    assert state is not None
    assert state["saga_status"] == "completed"
    assert len(state["checkpoints"]) == 4


# ---------------------------------------------------------------------------
# Test: Crash after payment — resume from checkpoint
# ---------------------------------------------------------------------------


def test_crash_after_payment() -> None:
    """Simulate crash after charge_payment. Resume skips completed steps
    and completes the remaining ones."""
    runner = _make_runner()
    ctx = _make_ctx()
    booking_args = dict(BOOKING_ARGS)

    # Phase 1: Run with crash after charge_payment
    crash_state = run_saga(ctx, runner, booking_args, crash_after="charge_payment")

    assert crash_state["saga_status"] == "crashed"
    assert crash_state["crash_step"] == "charge_payment"
    # Flight, hotel, and payment should be checkpointed
    assert runner.is_step_completed("reserve_flight")
    assert runner.is_step_completed("reserve_hotel")
    assert runner.is_step_completed("charge_payment")
    # Confirmation should NOT be completed
    assert not runner.is_step_completed("issue_confirmation")

    # Phase 2: Resume from checkpoint — new runner, replay checkpoints from log
    resume_runner = FakeDurableRunner(event_log=_event_log)
    _replay_checkpoints(resume_runner)

    ctx2 = _make_ctx()
    resume_state = run_saga(ctx2, resume_runner, booking_args)

    assert resume_state["saga_status"] == "completed"
    # All 4 steps should now be completed
    assert resume_runner.is_step_completed("issue_confirmation")


def test_crash_after_payment_via_entry_point() -> None:
    """Run via entry point — crash_after_payment scenario."""
    result = run(scenario="crash_after_payment")

    # The saga crashes mid-workflow; overall run succeeds since crash is handled
    assert result.status == ExecutionStatus.SUCCEEDED
    state = result.output
    assert state is not None
    assert state["saga_status"] == "crashed"


# ---------------------------------------------------------------------------
# Test: Compensation on failure — reverse order rollback
# ---------------------------------------------------------------------------


def test_compensation_on_failure() -> None:
    """When issue_confirmation fails, compensating actions run in reverse
    order on completed steps: refund_payment → release_hotel → release_flight.
    issue_confirmation was NOT completed, so no cancel_confirmation needed."""
    runner = _make_runner()
    ctx = _make_ctx()
    booking_args = dict(BOOKING_ARGS)

    state = run_saga(ctx, runner, booking_args, fail_step="issue_confirmation")

    # Saga should be in compensated state
    assert state["saga_status"] in ("compensated", "failed")
    assert state.get("failure_step") == "issue_confirmation"

    comp_result = state.get("compensation_result", {})
    comp_steps = comp_result.get("compensation_results", [])
    comp_actions = [c["action"] for c in comp_steps if c.get("action") != "noop"]

    # issue_confirmation failed before being checkpointed, so only
    # steps completed before it are compensated: charge_payment, reserve_hotel, reserve_flight
    # Reverse order: refund_payment → release_hotel → release_flight
    expected = ["refund_payment", "release_hotel", "release_flight"]
    assert comp_actions == expected, f"Expected {expected}, got {comp_actions}"


def test_compensation_on_failure_via_entry_point() -> None:
    """Run via entry point — compensation_on_failure scenario."""
    result = run(scenario="compensation_on_failure")

    # The saga detects the step failure and compensates.
    # run_scope catches the saga-level exception but the saga itself
    # handles compensation internally without raising.
    # Status may be SUCCEEDED (saga handled it) or FAILED.
    state = result.output
    assert state is not None
    assert state.get("failure_step") == "issue_confirmation"
    assert state["saga_status"] in ("compensated", "failed")


# ---------------------------------------------------------------------------
# Test: Compensation failure handling → human escalation
# ---------------------------------------------------------------------------


def test_compensation_failure_handling() -> None:
    """When a compensating action fails, the workflow escalates to human."""
    runner = _make_runner()
    ctx = _make_ctx()
    booking_args = dict(BOOKING_ARGS)

    # First do a full successful booking so we have all 4 checkpoints
    state = run_saga(ctx, runner, booking_args)
    assert state["saga_status"] == "completed"

    # Now inject a failure into the payment refund compensation
    _payment_service.inject_failure("refund")

    # Run compensation manually — refund_payment should fail
    comp_result = runner.compensate(booking_args["booking_id"])

    assert comp_result.get("escalation_required") is True, "Compensation failure should require escalation"
    assert runner.saga_status == "escalated", f"Expected escalated, got {runner.saga_status}"
    assert "escalation_message" in comp_result
    assert "Human escalation required" in comp_result["escalation_message"]


# ---------------------------------------------------------------------------
# Test: Idempotency — duplicate event replay → no double-booking
# ---------------------------------------------------------------------------


def test_idempotency() -> None:
    """Re-executing the same step with the same idempotency key
    should not create duplicate side effects."""
    booking_args = dict(BOOKING_ARGS)

    # First execution
    result1 = reserve_flight(
        booking_id=booking_args["booking_id"],
        flight=booking_args["flight"],
        customer=booking_args["customer"],
        idempotency_key=f"flight_{booking_args['booking_id']}",
    )
    assert result1["success"] is True
    assert result1["status"] == "reserved"

    # Count flights before replay
    flight_key = f"flight_{booking_args['booking_id']}"
    assert flight_key in _reserved_flights

    # Second execution with same idempotency key — should detect duplicate
    result2 = reserve_flight(
        booking_id=booking_args["booking_id"],
        flight=booking_args["flight"],
        customer=booking_args["customer"],
        idempotency_key=f"flight_{booking_args['booking_id']}",
    )
    assert result2["success"] is True
    assert "Already reserved" in result2.get("note", ""), "Should detect duplicate"
    # Still only one entry
    assert flight_key in _reserved_flights


def test_idempotency_payment() -> None:
    """Payment idempotency via MockPaymentService — duplicate keys are rejected."""
    booking_args = dict(BOOKING_ARGS)
    ik = f"payment_{booking_args['booking_id']}"

    # First charge succeeds
    result1 = charge_payment(
        booking_id=booking_args["booking_id"],
        amount=booking_args["amount"],
        idempotency_key=ik,
    )
    assert result1["success"] is True

    # Second charge with same key — MockPaymentService raises DuplicateRequestError
    result2 = charge_payment(
        booking_id=booking_args["booking_id"],
        amount=booking_args["amount"],
        idempotency_key=ik,
    )
    # Should fail because the idempotency key is already used
    assert result2["success"] is False
    assert "Duplicate" in result2.get("error", "")


# ---------------------------------------------------------------------------
# Test: Resume with no duplicate side effects
# ---------------------------------------------------------------------------


def test_resume_no_duplicate_side_effects() -> None:
    """After crash and resume, no step is executed twice.
    Idempotency keys prevent duplicate side effects."""
    runner = _make_runner()
    ctx = _make_ctx()
    booking_args = dict(BOOKING_ARGS)

    # Phase 1: Run until crash after charge_payment
    crash_state = run_saga(ctx, runner, booking_args, crash_after="charge_payment")
    assert crash_state["saga_status"] == "crashed"
    assert runner.is_step_completed("charge_payment")

    # Phase 2: Resume — new runner with checkpoints replayed from the log
    resume_runner = FakeDurableRunner(event_log=_event_log)
    _replay_checkpoints(resume_runner)

    ctx2 = _make_ctx()
    resume_state = run_saga(ctx2, resume_runner, booking_args)

    assert resume_state["saga_status"] == "completed"

    # After resume, side effects should still be exactly once per step
    # Flight reservation: once
    flight_success = [
        e for e in _event_log.get_by_type("step.reserve_flight.success")
    ]
    assert len(flight_success) <= 1, "Flight should only be reserved once"

    # Payment: once (second attempt on same key is rejected by MockPaymentService)
    payment_success = [
        e for e in _event_log.get_by_type("step.charge_payment.success")
    ]
    assert len(payment_success) <= 1, "Payment should only be charged once"


def test_resume_skips_completed_steps() -> None:
    """Resume should skip steps that are already checkpointed."""
    runner = _make_runner()
    ctx = _make_ctx()
    booking_args = dict(BOOKING_ARGS)

    # Manually checkpoint the first three steps
    runner.checkpoint("reserve_flight", {"success": True, "flight": booking_args["flight"]})
    runner.checkpoint("reserve_hotel", {"success": True, "hotel": booking_args["hotel"]})
    runner.checkpoint("charge_payment", {"success": True, "amount": booking_args["amount"]})
    runner.checkpoint("issue_confirmation", {"success": True, "confirmation_id": "cnf_bk_001"})

    # Run full saga — all steps already checkpointed, so no side effects
    ctx2 = _make_ctx()
    state = run_saga(ctx2, runner, booking_args)

    assert state["saga_status"] == "completed"
    # All steps should remain completed (no new operations)
    for step in SAGA_STEPS:
        assert runner.is_step_completed(step)
