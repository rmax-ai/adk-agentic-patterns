# Pattern 14: Memory Partitioning

## Problem
An agent that accumulates all conversation history into one undifferentiated memory
store cannot distinguish ephemeral context from long-term facts. Over time, stale,
low-confidence, or malicious entries pollute retrieval; working data from the current
session bleeds into permanent stores; and the agent has no way to selectively
forget or budget its memory access.

## Pattern
Separate stores and interfaces for four memory types, each with explicit retention
policies and validation thresholds:

1. **Working Memory** — ephemeral, TTL-scoped data (e.g., "current task") available
   only during the current session. Short TTL (10 minutes).
2. **Session Memory** — session-scoped data persists across turns within the same
   session (e.g., conversation context, UI state). TTL of 1 hour.
3. **Episodic Memory** — permanent store for past interactions. No TTL, but
   retrievable with a budget limit.
4. **User Profile** — user preferences and high-confidence history. Updates require
   elevated confidence threshold (>= 0.7).

## Why This Pattern Is Justified
- Raw conversation dumping into long-term memory creates noise and security risks
- Different memory types need different confidence thresholds for writes
- Stale data must be evicted to maintain retrieval quality
- Retrieval budgets prevent the agent from consuming unbounded context
- Profile updates require higher confidence than ephemeral session notes

## Simpler Alternative
A single flat dict with no TTL or confidence checking. But this makes the agent
vulnerable to memory poisoning, context overflow, and stale data pollution.
Partitioned memory with validation is the minimal safe design.

## ADK Primitives Used
- `ScriptedModel` for deterministic offline testing
- `RunContext` for budget tracking, audit events, and state snapshots
- Pydantic contracts (`MemoryEntry`, `UserProfile`) for typed memory access

## Information Flow
```
User Query → Memory Agent
  ├─ Working Memory (ephemeral, 10 min TTL)
  │   └─ Write: confidence >= 0.3, TTL check on read
  ├─ Session Memory (session-scoped, 1 hr TTL)
  │   └─ Write: confidence >= 0.3, persists across turns
  ├─ Episodic Memory (permanent, no TTL)
  │   └─ Write: confidence >= 0.3, budgeted retrieval (max 10 entries)
  └─ User Profile (permanent)
      └─ Write: confidence >= 0.7, no raw conversation dumping
```

## Control Flow
1. Agent receives operation request
2. Budget check — stop if exhausted
3. Route to appropriate memory operation handler
4. For each write: validate confidence threshold
5. For each read: check staleness (TTL), apply retrieval budget
6. For user profile: require high confidence (0.7) for updates
7. Detect and block raw conversation dumping
8. Return structured result with state snapshot

## State Model
| Key | Writer | Readers | Scope |
|-----|--------|---------|-------|
| `working_memory{}` | Agent | Agent | Ephemeral (10 min TTL) |
| `session_memory{}` | Agent | Agent | Session (1 hr TTL) |
| `episodic_memory[]` | Agent | Agent | Permanent (no TTL) |
| `user_profile{}` | Agent | Agent | Permanent |

## State Ownership Table
| Key | Writer | Readers | Scope |
|-----|--------|---------|-------|
| `working_memory{}` | Agent | Agent | Per-session ephemeral |
| `session_memory{}` | Agent | Agent | Per-session persistent |
| `episodic_memory[]` | Agent | Agent | Cross-session permanent |
| `user_profile{}` | Agent | Agent | Cross-session permanent |

## Tool Permission Table
| Tool | Permission | Rate Limit | Calls |
|------|-----------|------------|-------|
| `write_working_memory` | Self (Agent) | Per-write | 1-3 |
| `read_working_memory` | Self (Agent) | Per-read | 1-3 |
| `write_session_memory` | Self (Agent) | Per-write | 1-3 |
| `read_session_memory` | Self (Agent) | Per-read | 1-3 |
| `write_episodic_memory` | Self (Agent) | Per-write | 1-3 |
| `read_episodic_memory` | Self (Agent) | Budgeted (max 10) | 1 |
| `update_user_profile` | Self (Agent) | High confidence (>=0.7) | 1-2 |
| `set_preference` | Self (Agent) | No threshold | 1-3 |

## Success Termination
- `SUCCEEDED` — memory operation completed with all validations passed
- Output contains operation results, entry data, and validation metadata

## Failure Termination
- `FAILED` — confidence threshold not met, stale entry missing, or raw dump detected
- `BUDGET_EXHAUSTED` — max model calls or tool calls exceeded

## Retry Policy
No retry — memory operations are idempotent and direct.

## Execution Budgets
- `max_model_calls`: 3
- `max_tool_calls`: 5

## How to Run Offline
```bash
uv run python -m examples.14_memory_partitioning.run
uv run python -m examples.14_memory_partitioning.run session
uv run python -m examples.14_memory_partitioning.run profile
uv run pytest examples/14_memory_partitioning/test_example.py -v
```

## How to Run with Gemini
```bash
PATTERNS_EXECUTION_MODE=live GOOGLE_API_KEY=... uv run python -m examples.14_memory_partitioning.run
```

## Expected Output
See `expected/success.json` — successful memory operation with all validations passed.
See `expected/failure.json` — memory poisoning prevented (low confidence rejected).

## Tests Included
- `test_working_memory` — temporary data available during session
- `test_working_memory_state_keys` — state has working_memory key
- `test_session_memory` — session-scoped data persists across turns
- `test_session_memory_state_keys` — state has session_memory key
- `test_episodic_memory` — past interactions retrievable with budget
- `test_episodic_memory_state_keys` — state has episodic_memory key
- `test_user_profile` — preferences loaded, updated with high confidence only
- `test_user_profile_state_keys` — state has user_profile key
- `test_stale_memory` — expired entries not returned
- `test_memory_poisoning` — low-confidence injection rejected
- `test_no_raw_conversation_dumping` — raw chat history not in long-term memory
- `test_retrieval_budget` — max entries returned respected (budget=10)
- `test_budget_max_model_calls` — exactly 3 model calls max
- `test_audit_events_present` — audit trail recorded

## Common Failure Modes
- Low confidence notes failing to write (expected — they should fail)
- Stale entries being evicted before read (expected — TTL enforcement)
- Raw conversation detected and blocked (expected — safety mechanism)

## Production-Hardening Requirements
- Replace dict-based stores with a persistent database (SQLite, PostgreSQL)
- Add encryption for user profile and episodic memory
- Add user-facing commands for manual memory management (forget, archive)
- Add telemetry for memory usage patterns and poisoning attempts
- Implement time-aware decay for episodic memory relevance scoring
- Add hierarchical TTLs (session-level + entry-level)

## Related Patterns
- `bounded-loop-agent` — when bounded iteration needs memory across turns
- `tool-using-agent` — when external tools need to read/write memory stores
- `react-loop` — when the agent needs memory for chain-of-thought reasoning

## Anti-Pattern Demonstrated or Avoided
- **Avoided:** Single monolithic memory store with no partitioning
- **Avoided:** Raw conversation history dumped into long-term storage
- **Avoided:** Trusting low-confidence writes without validation
- **Avoided:** Stale data accumulating without eviction
- **Avoided:** Unbounded memory retrieval with no budget
- **Demonstrated:** Confidence-thresholded writes per memory type
- **Demonstrated:** Separate retention policies (TTL) per store
- **Demonstrated:** Retrieval budget enforcement
- **Demonstrated:** Memory poisoning protection via confidence grading
