# Pattern 03: Parallel Fan-Out/Gather

**Scenario:** Evaluate a vendor simultaneously for security, legal, operational, and financial concerns.

## Description

This pattern demonstrates parallel fan-out/gather using `asyncio.gather`. Four independent evaluation branches run concurrently, each writing to a unique state key. After all branches complete, a synthesis step aggregates the results into a final recommendation.

## State Keys

| Key | Description |
|-----|-------------|
| `security_eval` | Security posture evaluation (score, issues, summary) |
| `legal_eval` | Legal compliance evaluation (score, issues, summary) |
| `operational_eval` | Operational readiness evaluation (score, issues, summary) |
| `financial_eval` | Financial health evaluation (score, issues, summary) |
| `synthesis` | Aggregated final recommendation (overall_score, recommendation, summary) |

## Budget

- `max_model_calls`: 5 (4 branches + 1 synthesis)
- `max_tool_calls`: 0

## Behavior

- **Fail-fast mode** (`fail_fast=True`): A single branch failure immediately cancels all other branches via `asyncio.gather(return_exceptions=False)`. The run status is `FAILED`.
- **Partial mode** (`fail_fast=False`): Branch failures are collected as exceptions via `return_exceptions=True`. Surviving branches return with `PARTIAL` status and partial results.

## Running

```bash
# Success scenario
uv run python -m examples.03_parallel_fanout_gather.run

# Fail-fast scenario
uv run python -m examples.03_parallel_fanout_gather.run fail_fast

# Run tests
uv run pytest examples/03_parallel_fanout_gather/test_example.py -v
```

## Tests

| Test | Description |
|------|-------------|
| `test_all_branches_succeed` | All 4 evaluations and synthesis complete successfully |
| `test_fail_fast` | One branch failure stops all others immediately |
| `test_partial_results` | One branch failure returns 3/4 partial results |
| `test_parallel_speedup` | With MockClock, proves concurrent execution (4x speedup) |
| `test_no_state_collisions` | Each branch writes to a unique state key |
