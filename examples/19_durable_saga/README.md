# Pattern 19: Durable SAGA

Mocked travel booking workflow with append-only event log, checkpointing,
idempotency, crash recovery, and compensating rollback.

## Scenario

A travel booking workflow with four steps:

1. **Reserve flight** — book a flight for the customer
2. **Reserve hotel** — book a hotel room
3. **Charge payment** — authorize and capture payment via `MockPaymentService`
4. **Issue confirmation** — finalize the booking

If any step fails, **compensating actions** run in reverse order to undo
completed steps:

- Cancel confirmation
- Refund payment
- Release hotel
- Release flight

If compensation itself fails, the workflow **escalates to a human**.

## Key Concepts

| Concept | Implementation |
|---|---|
| Append-only event log | `EventLog` from `adk_patterns.mocks.event_log` |
| Checkpointing | After every step, save result to `checkpoints{}` dict |
| Idempotency | Each step has an `idempotency_key` — replaying skips completed steps |
| Crash recovery | `resume_saga()` replays events and skips checkpointed steps |
| Compensation | Reverse-order rollback via `FakeDurableRunner.compensate()` |
| Failure escalation | When compensation fails, `saga_status` = `"escalated"` |

## State Keys

- `event_log[]` — append-only list of `LogEntry` objects
- `checkpoints{}` — map of step name to completed checkpoint
- `saga_status` — one of: `pending`, `completed`, `failed`, `crashed`, `compensating`, `compensated`, `escalated`
- `compensation_log[]` — list of compensation action records

## How to Run

```bash
# Full successful booking
uv run python -m examples.19_durable_saga.run

# With crash after payment (tests resume)
uv run python -m examples.19_durable_saga.run crash_after_payment
```

## How to Test

```bash
uv run pytest examples/19_durable_saga/test_example.py -v
```

## Tests

| Test | What it proves |
|---|---|
| `test_full_booking_success` | All 4 steps complete successfully |
| `test_crash_after_payment` | Resume from checkpoint skips completed steps |
| `test_compensation_on_failure` | Reverse-order rollback on step failure |
| `test_compensation_failure_handling` | Compensation failure → human escalation |
| `test_idempotency` | Duplicate event replay → no double-booking |
| `test_resume_no_duplicate_side_effects` | Restarting doesn't duplicate side effects |

## Replacing FakeDurableRunner with Temporal

The `FakeDurableRunner` is a local event-sourced implementation. To use
Temporal instead:

1. **Define a Temporal Workflow** with Activities for each step
2. **Replace checkpointing** with Temporal's built-in workflow state
   (automatic on `yield` or `await`)
3. **Use Temporal's compensation API** for rollback:
   ```python
   async def book_travel():
       flight = await compensate.execute_activity(reserve_flight)
       hotel = await compensate.execute_activity(reserve_hotel)
       payment = await compensate.execute_activity(charge_payment)
       confirmation = await execute_activity(issue_confirmation)
       # If confirmation fails, Temporal automatically calls compensations
       # for flight, hotel, and payment in reverse order
   ```
4. **Idempotency** is handled by Temporal's unique workflow ID — duplicate
   starts return the existing result

## Replacing with Persistent ADK Session Service

1. **Checkpoints → ADK Session State**: Store `checkpoints` and `saga_status`
   in the ADK session's persistent state store instead of an in-memory dict
2. **Event Log → Database**: Replace the in-memory `EventLog` with a DB-backed
   append-only event store
3. **Runner → ADK Agent Loop**: Use ADK's `before_model_callback` /
   `after_model_callback` to checkpoint after each tool call
4. **Resume**: On session resume, load state from ADK session store, replay
   events from the DB log, skip checkpointed steps

## Comparison Matrix

| Dimension | Score | Notes |
|---|---|---|
| Determinism | 8 | Checkpoint and replay are fully deterministic in offline mode |
| Adaptability | 5 | Step order is fixed but compensation actions are configurable |
| State Complexity | 7 | Four state keys, event log + checkpoints + compensation log |
| Coordination Complexity | 3 | Single saga runner, no distributed coordination |
| Testability | 10 | Fully mockable, deterministic replay, no external dependencies |
| Failure Containment | 8 | Compensation rollback + human escalation for incomplete rollbacks |
| Security Isolation | 3 | No cross-saga isolation in this simple mock implementation |
| Latency | medium | Sequential steps, checkpoint writes after each |
| Token Consumption | low | No model calls in the core saga loop |
| Resumability | Yes | Full checkpoint/resume support |
| Human Controllability | 5 | Escalation on compensation failure |
| Operational Burden | low | Single-process, in-memory, no infrastructure |

## Use Cases

- **Travel booking** (as demonstrated)
- **E-commerce order fulfillment**: reserve inventory → charge payment → ship
- **Financial transfers**: debit source → credit destination → confirm
- **Multi-step provisioning**: allocate resources → configure → deploy
- **Any workflow requiring exactly-once execution with rollback guarantees**
