# Pattern 23: Composed Production Reference System

**Capstone pattern** combining 9 sub-patterns into a single regulated
customer-support workflow. Demonstrates how to compose independent agentic
patterns into a coherent, production-ready system with policy enforcement,
specialist routing, RAG, tool execution, evaluation, human approval,
event logging, observability, and failure recovery.

## Pattern Overview

```
User Request
    │
    ▼
┌─────────────────────┐
│ 1. Policy Gate      │  ← Guardrails: block unsafe input
│    (guardrails)     │
└─────────┬───────────┘
          │ (passed)
          ▼
┌─────────────────────┐
│ 2. Router-          │  ← Classify: account / billing / technical
│    Specialist       │
└─────────┬───────────┘
          │ (routed)
          ▼
┌─────────────────────┐
│ 3. Agentic RAG      │  ← Retrieve relevant policy documents
└─────────┬───────────┘
          │ (docs retrieved)
          ▼
┌─────────────────────┐
│ 4. Tool-Using Agent │  ← Execute domain-specific tools
│    (isolated tools) │
└─────────┬───────────┘
          │ (tool results)
          ▼
┌─────────────────────┐
│ 5. Evaluate Answer  │  ← Verify against rubric
│    (evaluator)      │
└─────────┬───────────┘
          │ (for refund proposals)
          ▼
┌─────────────────────┐
│ 6. Human Approval   │  ← Refund requires human approval
│    Gate             │
└─────────┬───────────┘
          │ (approved / rejected)
          ▼
┌─────────────────────┐
│ 7. Refund Execution │  ← Executes with idempotency key
│    (idempotent)     │
└─────────────────────┘
```

Every transition is:
- **Logged** to a durable event log (sub-pattern 7)
- **Traced** with observability spans (sub-pattern 8)
- **Budget-checked** against max_model_calls / max_tool_calls / max_iterations
- **Recoverable** via checkpoint/resume on transient errors (sub-pattern 9)

## Sub-Patterns Composed

| # | Pattern | Role |
|---|---------|------|
| 1 | **Guardrails Policy Gate** | Input validation: block unsafe requests before any processing |
| 2 | **Router-Specialist** | Classify request → route to account/billing/technical specialist |
| 3 | **Agentic RAG** | Retrieve relevant policy documents for the specialist |
| 4 | **Tool-Using Agent** | Execute domain-specific tools with isolation |
| 5 | **Evaluator-Optimizer** | Verify answer against rubric (correctness, completeness, safety) |
| 6 | **Human Approval Gate** | Require human approval for refund proposals |
| 7 | **Durable Event Log** | Record every phase transition for audit |
| 8 | **Observability** | Trace all spans with timing |
| 9 | **Failure Recovery** | Retry on transient errors, checkpoint/resume |

## Scenarios

| Scenario | Route | RAG | Tools | Evaluator | Approval | Refund |
|----------|-------|-----|-------|-----------|----------|--------|
| `read_only_inquiry` | account | ✅ | ✅ (read) | ❌ skipped | ❌ | ❌ |
| `billing_dispute` | billing | ✅ | ✅ (read) | ✅ | ❌ | ❌ |
| `refund_approved` | billing | ✅ | ✅ (read) | ✅ | ✅ approve | ✅ |
| `refund_rejected` | billing | ✅ | ✅ (read) | ✅ | ✅ reject | ❌ |

## Required Boundaries

- **Read operations** execute automatically without approval
- **Refund proposals** require evaluator verification
- **Refund writes** require authorization and human approval
- **Every write** receives an idempotency key (prevents duplicate execution)
- **Every transition** logged to the durable event log
- **Crash recovery**: checkpoint saved after RAG, can resume
- **Tool isolation**: no specialist receives tools outside its domain
- **Budget enforcement**: every loop and tool call is budgeted

## State Keys

```json
{
  "request": "string",
  "route": "account|billing|technical|blocked",
  "docs": [{"doc_id": "...", "content": "...", "score": 0.0}],
  "tool_results": [{"tool": "...", "result": {...}}],
  "answer": "string",
  "evaluator_scores": {"correctness": 0.0, "completeness": 0.0, "safety": 0.0, "overall": 0.0, "passed": bool},
  "approval": {"approved": bool, "reviewer": "string"},
  "refund_result": {"success": bool, "refund_id": "string"},
  "event_log": [{"phase": "...", "action": "...", "details": {...}}],
  "trace_id": "string"
}
```

## Budget

| Metric | Limit |
|--------|-------|
| max_model_calls | 10 |
| max_tool_calls | 15 |
| max_iterations | 5 |

## Running

```bash
# Read-only account inquiry (default)
python run.py

# Billing dispute
python run.py --scenario billing_dispute

# Refund approved
python run.py --scenario refund_approved

# Refund rejected
python run.py --scenario refund_rejected

# JSON output
python run.py --scenario billing_dispute --json
```

## Testing

```bash
# Run all tests
pytest test_example.py -v

# Run specific test category
pytest test_example.py -v -k "test_read_only_inquiry"
pytest test_example.py -v -k "test_refund"
pytest test_example.py -v -k "test_budget"
pytest test_example.py -v -k "test_tool_isolation"

# Run with coverage
pytest test_example.py -v --cov=agent --cov-report=term-missing
```

## Test Coverage (10 required tests + extras)

| Test | Description |
|------|-------------|
| `test_read_only_inquiry` | Account inquiry: classify → route → RAG → tool → answer, no approval |
| `test_billing_dispute` | Billing: route → RAG → tool → evaluate → answer |
| `test_refund_approved` | Refund: route → RAG → tool → evaluate → approve → refund |
| `test_refund_rejected` | Refund: route → RAG → tool → evaluate → reject → no refund |
| `test_policy_gate_blocks` | Unsafe input blocked at gate |
| `test_tool_isolation` | Account tools not available to billing specialist |
| `test_crash_resume` | Crash after RAG, resume completes |
| `test_idempotent_refund` | Same refund proposal twice, no duplicate execution |
| `test_event_log_complete` | All transitions recorded |
| `test_budget_enforcement` | Respects max_model_calls and max_tool_calls |

## Design Notes

- Each sub-pattern is a **distinct function** in `agent.py` for clarity
- The `composed_workflow()` function orchestrates all phases in sequence
- Mock stores are reset between tests via `autouse` fixture
- Policy gate uses keyword matching (deterministic, no model call)
- Router uses keyword scoring with deterministic fixture overrides for tests
- RAG uses `MockDocumentStore` with predefined similarity scores
- Tool isolation enforces `PermissionError` for cross-domain calls
- Approval gate uses `MockApprovalService` with auto-approve/reject modes
- Event log supports checkpointing for crash recovery
- Tracer records span names and timing for observability
- Retry uses exponential backoff via `RetryConfig`
