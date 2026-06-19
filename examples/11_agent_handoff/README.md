# Pattern 11: Agent Handoff

## Problem
A support agent needs to transfer a conversation to a refund specialist for refund processing, while preserving only necessary context, maintaining an audit trail, and handling rejection gracefully.

## Pattern
A two-phase pattern:
1. **Support Agent** — Processes the customer request and decides whether to hand off to a refund specialist
2. **Refund Specialist** — Evaluates the handoff request and either accepts (processes refund) or rejects (triggers fallback escalation)

Key behaviors:
- **Context minimisation** — Only relevant keys (`customer_id`, `invoice_id`, `issue_type`, `request_text`) are transferred; sensitive/internal keys are stripped
- **Explicit handoff reason** — Each handoff includes a typed `HandoffRequest` with a clear reason
- **Narrower permissions** — Refund specialist cannot access support tools (`lookup_customer`, `escalate`)
- **Handoff audit record** — Every handoff event (accepted/rejected) is recorded with full metadata
- **Rejected handoff fallback** — When the specialist rejects, the support agent escalates the issue

## Why This Pattern Is Justified
- Prevents unnecessary context leakage to specialist agents
- Provides clear audit trail for compliance
- Graceful degradation when specialist cannot process the request
- Security isolation through tool permission boundaries
- Typed contracts prevent unstructured handoff arguments

## Simpler Alternative
Single agent with all refund tools — but handoff enables specialised permission boundaries, context minimisation, and audit trails.

## ADK Primitives Used
- `ScriptedModel` (offline fake model for deterministic testing)
- `structured_response` (fixture-based model responses)
- `RunContext` (budget tracking, audit events, state snapshots)

## Information Flow
```
Customer Request → Support Agent (model) → HandoffRequest (typed)
                                              ↓
                                    Refund Specialist (model) → HandoffResponse
                                         ↓              ↓
                                   [accepted]       [rejected]
                                       ↓                ↓
                              Refund Tools        Support Fallback
                              (lookup_refund,     (escalate)
                               process_refund)
                                       ↓                ↓
                                refund_result      escalation record
```

## Control Flow
1. Support agent receives customer request
2. Model call #1: Support agent produces `HandoffRequest` (reason + minimised context)
3. Context is minimised — only relevant keys transferred
4. Model call #2: Refund specialist evaluates handoff and produces `HandoffResponse`
5. If accepted: refund specialist executes `lookup_refund` and `process_refund`
6. If rejected: support agent executes `escalate` as fallback
7. Handoff event recorded in audit trail
8. Return `conversation_context`, `handoff_record`, `refund_result`

## State Model
- Transient state per request — no persistent storage
- State keys: `conversation_context`, `handoff_record`, `refund_result`

## State Ownership Table
| Key | Writer | Readers | Scope |
|-----|--------|---------|-------|
| conversation_context | Support agent | Refund specialist, Output | Per-request |
| handoff_record | Support + Refund | Output, Audit | Per-request |
| refund_result | Refund specialist or Support (fallback) | Output | Per-request |

## Tool Permission Table
| Tool Set | Owner Agent | Permissions |
|----------|-------------|-------------|
| lookup_customer, escalate | support | support only |
| lookup_refund, process_refund | refund_specialist | refund_specialist only |

## Success Termination
Support → accepted handoff → refund specialist processes refund → typed `refund_result` returned.

## Failure Termination
- Handoff rejected → support escalates (graceful fallback)
- Permission violation → `PermissionError`
- Budget exhausted

## Retry Policy
No retry — single-pass handoff evaluation.

## Execution Budgets
- max_model_calls: 2
- max_tool_calls: 5
- max_iterations: 0

## How to Run Offline
```bash
uv run python -m examples.11_agent_handoff.run
uv run python -m examples.11_agent_handoff.run handoff_accepted
uv run python -m examples.11_agent_handoff.run handoff_rejected
uv run pytest examples/11_agent_handoff/test_example.py -v
```

## How to Run with Gemini
```bash
PATTERNS_EXECUTION_MODE=live GOOGLE_API_KEY=... uv run python -m examples.11_agent_handoff.run
```

## Expected Output
See `expected/success.json` — accepted handoff with refund processing.
See `expected/failure.json` — rejected handoff with escalation fallback.

## Tests Included
- `test_handoff_accepted` — support transfers to refund, context preserved
- `test_handoff_rejected` — refund specialist rejects, fallback to support
- `test_context_minimization` — only relevant keys transferred
- `test_narrower_permissions` — refund specialist cannot access support tools
- `test_handoff_audit` — handoff event recorded
- Plus unit tests for contracts, context minimisation, permission checks, budget enforcement, state keys, and tool execution

## Common Failure Modes
- Handoff rejected → escalates to human (handled)
- Refund specialist tries to use support tool → `PermissionError` (handled)
- Missing fixture key → defaults to empty `HandoffResponse`

## Production-Hardening Requirements
- Replace scripted model with real Gemini/Claude
- Add prompt versioning
- Add telemetry export (OpenTelemetry collector)
- Add human-in-the-loop approval for high-value refunds
- Add handoff timeout detection

## Related Patterns
- `router-specialist` — simpler routing without explicit handoff contracts
- `guardrails-policy-gate` — for pre-handoff policy checks
- `human-approval-gate` — for refund amount approval thresholds

## Anti-Pattern Demonstrated or Avoided
- **Avoided:** Passing full conversation context (data leakage risk)
- **Avoided:** Unstructured handoff messages (no typed contracts)
- **Avoided:** Silent handoff without audit trail
- **Demonstrated:** Context minimisation with typed handoff contracts
