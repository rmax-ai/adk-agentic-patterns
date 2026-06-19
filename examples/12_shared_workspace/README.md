# Pattern 12: Shared Workspace / Blackboard

**Scenario:** Multiple research workers contribute claims to a shared evidence board. The board is append-only with versioned, author-identified entries. A synthesizer reads only accepted claims to produce a summary.

## Description

This pattern demonstrates a shared workspace (blackboard) where multiple agents can independently contribute and modify shared state through strict contracts. Key characteristics:

- **Append-only workspace**: Once a claim is added, it cannot be overwritten. New claims must have unique IDs.
- **Versioned entries**: Each claim carries a version field incremented on update, enabling optimistic locking.
- **Author identity**: Every claim is tagged with its author's identity for provenance tracking.
- **Optimistic locking**: Status updates require the expected version; concurrent updates with stale versions are rejected.
- **Synthesizer isolation**: The synthesizer reads only accepted claims — rejected claims are excluded from synthesis.

Shared workspaces increase coordination complexity because multiple agents operate on the same data structure, requiring version checking, conflict detection, and append-only semantics to prevent data corruption.

## State Keys

| Key | Description |
|-----|-------------|
| `evidence_board{}` | Dict of claim_id -> Claim dict (append-only, versioned) |
| `synthesizer_output` | Structured synthesis result (summary, accepted_count, claim_ids) |

## Contracts

| Field | Type | Description |
|-------|------|-------------|
| `Claim.id` | `str` | Unique claim identifier |
| `Claim.author` | `str` | Who contributed the claim |
| `Claim.text` | `str` | The claim statement |
| `Claim.evidence` | `str` | Supporting evidence or citation |
| `Claim.confidence` | `float` | Confidence score (0.0 – 1.0) |
| `Claim.status` | `str` | One of: pending, accepted, rejected |
| `Claim.version` | `int` | Optimistic-lock version (incremented on update) |

## Budget

- `max_model_calls`: 3 (3 workers, synthesizer uses board fallback)
- `max_tool_calls`: 5

## Behavior

- **Success scenario**: 3 workers contribute claims, all are accepted, synthesizer produces summary of all 3.
- **Append-only scenario**: Worker adds a claim; attempt to overwrite same ID is rejected.
- **Version conflict scenario**: Worker adds a claim; first update succeeds, second update with stale version fails.
- **Synthesizer rejects scenario**: 3 claims added; only one accepted; synthesizer reads only the accepted claim.

## Running

```bash
# Success scenario (default)
uv run python -m examples.12_shared_workspace.run

# Append-only test
uv run python -m examples.12_shared_workspace.run append_only

# Version conflict test
uv run python -m examples.12_shared_workspace.run version_conflict

# Synthesizer rejects scenario
uv run python -m examples.12_shared_workspace.run synthesizer_rejected

# Run tests
uv run pytest examples/12_shared_workspace/test_example.py -v
```

## Tests

| Test | Description |
|------|-------------|
| `test_workers_contribute` | 3 workers add claims, all appear on board |
| `test_append_only` | Overwrite attempt rejected — append-only invariant |
| `test_optimistic_locking` | Version conflict triggers retry |
| `test_author_identity` | Each claim has correct author identity |
| `test_synthesizer_reads_accepted_only` | Rejected claims excluded from synthesis |
| `test_conflict_detection` | Concurrent write to same key detected via version mismatch |
