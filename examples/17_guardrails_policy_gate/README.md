# Pattern 17: Guardrails Policy Gate

Classify and block unsafe/unauthorized payment requests using a multi-layer guardrail system.

## Scenario

A payment-processing assistant handles payment requests with three guardrail layers:

1. **Pre-model input policy** — checks the user's query before the model sees it
2. **Pre-tool authorization policy** — checks before each tool executes
3. **Post-tool output policy** — checks the tool's output before returning it

## Guardrail Architecture

```
User Query
    │
    ▼
┌─────────────────────────────────────┐
│  Layer 1: Pre-Model Input Policy    │
│  ┌───────────────────────────────┐  │
│  │ Deterministic Keyword Filter  │──│── Blocked (deny)
│  └───────────┬───────────────────┘  │
│  ┌───────────▼───────────────────┐  │
│  │ Prompt Injection Detector     │──│── Blocked (deny)
│  └───────────┬───────────────────┘  │
└──────────────┼──────────────────────┘
               │ Allowed
               ▼
         ┌──────────┐
         │  Model   │
         └────┬─────┘
              │ Tool Call
              ▼
┌─────────────────────────────────────┐
│  Layer 2: Pre-Tool Authorization    │
│  ┌───────────────────────────────┐  │
│  │ MockAuthorizationService      │──│── Denied (blocked)
│  └───────────┬───────────────────┘  │
│  ┌───────────▼───────────────────┐  │
│  │ Fail-Closed (write) /         │──│── Denied / Allowed-Degraded
│  │ Fail-Open (read) on Degraded  │  │
│  └───────────┬───────────────────┘  │
└──────────────┼──────────────────────┘
               │ Allowed
               ▼
         ┌──────────┐
         │ Tool     │
         └────┬─────┘
              │ Result
              ▼
┌─────────────────────────────────────┐
│  Layer 3: Post-Tool Output Policy   │
│  ┌───────────────────────────────┐  │
│  │ Sensitive Data Scanner       │──│── Blocked (scrubbed)
│  └───────────┬───────────────────┘  │
└──────────────┼──────────────────────┘
               │ Clean
               ▼
         Final Answer
```

## Policy Verdicts

| Verdict | Meaning |
|---------|---------|
| `allow` | Request/action passed all policy checks |
| `deny` | Request/action blocked by policy |
| `block` | Output blocked by post-tool policy |
| `allow_degraded` | Read operation allowed during degradation |

## Reason Codes

| Code | Phase | Description |
|------|-------|-------------|
| `no_keywords_matched` | pre_model | Query passed keyword filter |
| `keyword_ignore_rules` | pre_model | "ignore rules/instructions" detected |
| `keyword_forget_instructions` | pre_model | "forget instructions" detected |
| `keyword_free_agent` | pre_model | "you are free agent" detected |
| `keyword_bypass` | pre_model | "bypass security" detected |
| `keyword_override` | pre_model | "override policies" detected |
| `keyword_disregard` | pre_model | "disregard instructions" detected |
| `keyword_role_reversal` | pre_model | Role reversal attempt detected |
| `injection_free_agent` | pre_model | Prompt injection: agent liberation |
| `injection_ignore` | pre_model | Prompt injection: ignore-and-replace |
| `injection_forget` | pre_model | Prompt injection: instruction amnesia |
| `injection_new_identity` | pre_model | Prompt injection: identity override |
| `injection_system_prompt` | pre_model | Prompt injection: system prompt override |
| `authorized` | pre_tool | Tool is authorized to execute |
| `unauthorized` | pre_tool | Tool denied by authorization service |
| `fail_closed_write` | pre_tool | Write denied during degradation |
| `fail_open_read` | pre_tool | Read allowed during degradation |
| `ssn_detected` | post_tool | SSN pattern found in output |
| `pan_detected` | post_tool | Credit card PAN found in output |
| `sensitive_label` | post_tool | Sensitive label in output |

## State Keys

- `policy_verdicts[]` — list of all policy verdicts by phase
- `blocked_requests[]` — requests blocked by any guardrail layer
- `authorized_actions[]` — actions that passed authorization
- `tool_results{}` — results of executed tool calls
- `final_answer` — the model's final textual answer
- `degraded` — whether the system is in degraded mode

## Budget

- `max_model_calls=2`
- `max_tool_calls=3`

## Running

```bash
# Default scenario
uv run python -m examples.17_guardrails_policy_gate.run

# Specific scenario
uv run python -m examples.17_guardrails_policy_gate.run allow_safe_request
uv run python -m examples.17_guardrails_policy_gate.run block_unsafe_request
uv run python -m examples.17_guardrails_policy_gate.run prompt_injection_blocked
uv run python -m examples.17_guardrails_policy_gate.run pre_tool_authorization
uv run python -m examples.17_guardrails_policy_gate.run post_tool_output_policy
uv run python -m examples.17_guardrails_policy_gate.run fail_closed_write
uv run python -m examples.17_guardrails_policy_gate.run fail_open_read
```

## Testing

```bash
uv run pytest examples/17_guardrails_policy_gate/test_example.py -v
```
