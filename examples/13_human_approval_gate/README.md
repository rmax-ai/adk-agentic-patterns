# Pattern 13: Human Approval Gate

## Problem
An agent must process refunds but lacks authority to execute them without human
approval. The workflow suspends in a pending/checkpoint state, then resumes on
approve, reject, timeout, or amend. The agent cannot self-approve.

## Pattern
The agent proposes a refund, which enters a **pending** state. A human reviewer
must explicitly approve or reject it via a mock approval service. The workflow
is resumable: the same pending proposal can be checked again later. The
`execute_refund` function is idempotent — calling it twice does not create a
duplicate refund.

## Why This Pattern Is Justified
- Refunds involve real money — they must not execute without human authorization
- Workflow suspension preserves state across human review cycles
- Reviewer identity and timestamp provide a basic audit trail
- Idempotent execution prevents accidental duplicate payouts on resume

## Simpler Alternative
Skip approval entirely (anti-pattern for financial operations). Or use a binary
flag with no reviewer identity — but audit/compliance requirements usually
demand who approved what, and when.

## ADK Primitives Used
- `ScriptedModel` (offline fake model with response sequences)
- `MockApprovalService` (mock approval service from shared mocks)
- Manual state management with pending/approved/rejected/timed_out states
- Tool-based workflow: propose → check → execute or escalate

## Information Flow
```
User Request ("Process refund of $150")
       ↓
Agent submits proposal → MockApprovalService (pending)
       ↓
Agent checks approval status → MockApprovalService
       ↓
Approved? → Agent calls execute_refund → RefundResult
Rejected? → Agent informs user
Timed out? → Agent escalates to supervisor
```

## Control Flow
1. User requests a refund
2. Agent calls `submit_refund_proposal(amount, reason, customer_id)`
3. Proposal enters `pending` state in MockApprovalService
4. Agent calls `check_approval_status(proposal_id)` to poll for decision
5. If **approved**: agent calls `execute_refund(proposal_id)` — idempotent
6. If **rejected**: agent informs user, no refund executed
7. If **timed out**: agent escalates to supervisor for manual handling
8. Agent **cannot** self-approve — `approve_refund()` returns error if
   `reviewer="agent"`

## State Model
The run output carries three state keys reflecting the approval lifecycle.

## State Ownership Table

| Key | Writer | Readers | Scope |
|-----|--------|---------|-------|
| proposal | submit_refund_proposal | check_approval_status, execute_refund, Output | Workflow |
| approval_status | submit_refund_proposal, check_approval_status | execute_refund, Output | Workflow |
| refund_result | execute_refund | Output | Workflow |

## Tool Permission Table

| Tool | Agent | Permissions |
|------|-------|-------------|
| submit_refund_proposal | Agent | Write (create proposal) |
| check_approval_status | Agent, Human | Read |
| execute_refund | Agent | Write (idempotent) |
| approve_refund | Human only | Write — Agent blocked (self-approve) |
| reject_refund | Human only | Write |

## Success Termination
Proposal is approved by a human reviewer → refund is executed → `refund_result`
contains `success: true` with a refund ID.

## Failure Termination
- Proposal is rejected → `refund_result` is `None`, agent informs user of denial
- Proposal times out → `refund_result` is `None`, agent escalates to supervisor
- Agent tries to self-approve → tool returns error with self-approval message
- Budget exhausted → status `BUDGET_EXHAUSTED`

## Retry Policy
No retry — the workflow pauses and waits for human input. Resuming the same
state is safe (idempotent). The agent polls for status rather than retrying the
proposal submission.

## Execution Budgets
- max_model_calls: 2
- max_tool_calls: 5
- max_iterations: 3

## How to Run Offline
```bash
uv run python -m examples.13_human_approval_gate.run
uv run python -m examples.13_human_approval_gate.run approved
uv run python -m examples.13_human_approval_gate.run rejected
uv run pytest examples/13_human_approval_gate/test_example.py -v
```

## How to Run with Gemini
```bash
PATTERNS_EXECUTION_MODE=live GOOGLE_API_KEY=... uv run python -m examples.13_human_approval_gate.run
```

## Expected Output
See `expected/success.json` — approved refund with refund_id and final answer.
See `expected/failure.json` — rejected refund with no refund_result.

## Tests Included
- `test_approval_required` — agent proposes, workflow suspends pending approval
- `test_approved` — approval granted, refund executed
- `test_rejected` — approval denied, refund not executed
- `test_timeout` — approval times out, fallback escalation
- `test_agent_cannot_self_approve` — agent blocked from approving own proposal
- `test_idempotent_resume` — resume with same state twice, no duplicate refund

## Common Failure Modes
- Missing fixture key → `ScriptedModel` returns default empty response, agent
  may stall or produce incorrect output
- Approval service not configured for scenario → proposal stays pending forever
- Self-approval attempt → tool returns error, agent must inform user
- Executing without checking status → `execute_refund` fails with non-approved
  status

## Production-Hardening Requirements
- Replace mock approval service with real human-in-the-loop system (Slack
  approval, Jira ticket, etc.)
- Add authenticated reviewer identity with cryptographic signatures
- Add proper workflow persistence (database-backed checkpoints, not in-memory)
- Add notification system: email/Slack to reviewer when proposal is submitted
- Add escalation rules: auto-escalate if no response within SLA
- Add concurrent-approval guarding: prevent double-spending
- Add full audit trail with immutable event log
- Add timeout configuration per proposal tier (amount-based SLA tiers)
- Add amendment support: reviewer can modify amount/reason before approving

## Related Patterns
- `tool-using-agent` — baseline tool-calling agent structure this builds on
- `dynamic-workflow` — when the approval path is determined at runtime
- `bounded-loop-agent` — when the agent needs internal iteration before/after
  the approval gate

## Anti-Pattern Demonstrated or Avoided
- **Avoided:** Agent executing side effects without oversight
- **Avoided:** Self-approval (agent approving its own proposals)
- **Avoided:** Double-refund through idempotent execution
- **Avoided:** Silent state loss on workflow pause (state preserved in output)
