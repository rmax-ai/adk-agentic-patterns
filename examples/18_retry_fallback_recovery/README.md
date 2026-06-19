# Pattern 18: Retry Fallback Recovery

Retrieve account data from an unreliable mocked service with exponential backoff, circuit breaker, fallback cache, and dead-letter recording.

## Problem

External services are unreliable. Network blips, rate limits, and temporary outages cause transient errors, while missing resources or auth failures cause permanent errors. Naive retries make things worse — they waste resources, amplify load, and offer no recovery path.

## Solution

A deterministic retry loop that:

1. **Classifies errors** via a single model call — transient errors (retriable) vs permanent errors (non-retriable)
2. **Applies bounded exponential backoff** with deterministic jitter between retries
3. **Uses a circuit breaker** that opens after 3 consecutive failures and resets after a timeout
4. **Falls back to a cache** of stale data when the circuit is open
5. **Records dead-letter records** for requests that cannot be recovered

The LLM is invoked exactly once for error classification. The retry loop itself is pure Python — no unnecessary model calls.

## State Machine

```
                    ┌──────────┐
    classify ──────►│  START   │
                    └────┬─────┘
                         │
                    ┌────▼─────┐
         ┌─────────►│  ATTEMPT │◄────────────┐
         │          └────┬─────┘             │
         │               │                   │
         │    ┌──────────┼──────────┐        │
         │    ▼          ▼          ▼        │
         │ success  transient   permanent    │
         │    │          │          │        │
         │    ▼          ▼          ▼        │
         │  DONE    backoff +   dead_letter  │
         │           retry ──────┘           │
         │              │                    │
         │         circuit_open?             │
         │              │                    │
         │         ┌────┴────┐               │
         │      yes│         │no             │
         │         ▼         └───────────────┘
         │    fallback
         │      cache
         │         │
         │     ┌───┴───┐
         │   hit│      │miss
         │     ▼       ▼
         │   DONE  dead_letter
         │
         └── retry_count < max_attempts
```

## State Keys

| Key | Type | Description |
|-----|------|-------------|
| `account_data` | `AccountData \| None` | Retrieved account payload or None |
| `retry_count` | `int` | Number of retry attempts made |
| `circuit_state` | `str` | `"closed"`, `"open"`, or `"half-open"` |
| `dead_letter` | `list[dict]` | Records of unrecoverable failures |

## Budget

| Resource | Limit |
|----------|-------|
| `max_model_calls` | 1 |
| `max_tool_calls` | 10 |

## Error Taxonomy

| Error Type | Retriable? | Example |
|------------|-----------|---------|
| `TransientError` | Yes | Timeout, rate limit, temporary unavailable |
| `PermanentError` | No | Account not found, unauthorized, invalid ID |

## Files

| File | Purpose |
|------|---------|
| `agent.py` | Core orchestration — model call + retry loop |
| `contracts.py` | Typed contracts and error taxonomy |
| `mocks.py` | MockAccountService + FallbackCache |
| `tools.py` | Tool functions (classify, get data, check circuit, dead letter) |
| `fixtures.py` | ScriptedModel fixture definitions |
| `run.py` | CLI entry point |
| `test_example.py` | 19 comprehensive tests |
| `expected/success.json` | Expected output for success scenario |
| `expected/failure.json` | Expected output for permanent error scenario |

## Usage

```bash
# Run default (success) scenario
uv run python -m examples.18_retry_fallback_recovery.run

# Run specific scenario
uv run python -m examples.18_retry_fallback_recovery.run success
uv run python -m examples.18_retry_fallback_recovery.run transient_then_success
uv run python -m examples.18_retry_fallback_recovery.run permanent_error

# Run all tests
uv run pytest examples/18_retry_fallback_recovery/test_example.py -v
```

## Test Scenarios

| Scenario | Behavior |
|----------|----------|
| `success` | First attempt succeeds immediately |
| `transient_then_success` | 2 transient errors, then success |
| `permanent_error` | Permanent error, dead letter recorded |
| `circuit_breaker` | 3 transient errors open the circuit |
| `fallback_cache` | Circuit opens, stale cache returned |
| `dead_letter` | Failed request recorded in dead letter |
| `exponential_backoff` | Delays verified to increase exponentially |
| `retry_exhaustion` | All max_attempts consumed, dead letter recorded |
