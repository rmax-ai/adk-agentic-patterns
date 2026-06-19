# Pattern 15: Agentic RAG

Answer multi-hop questions over a small local corpus using iterative retrieval and evidence tracking.

## Description

Retrieval-Augmented Generation (RAG) typically retrieves documents once and answers. **Agentic RAG** takes this further: the agent can iteratively refine its retrieval based on what it has already seen, building an **evidence ledger** that tracks exactly which documents support which claims.

This pattern demonstrates:

- **Multi-hop retrieval**: The agent retrieves documents, analyzes them, and decides whether it needs more information to answer the question.
- **Evidence ledger**: Tracks `doc_id → [claims supported]` — a transparent audit trail.
- **Citation validation**: After answer synthesis, every citation is verified against the evidence ledger.
- **Unsupported-claim rejection**: Claims that lack supporting documents are explicitly flagged.
- **Single-pass baseline comparison**: The same question answered with one-shot retrieval vs. iterative refinement.
- **Budget enforcement**: `max_model_calls=5`, `max_tool_calls=8`, `max_iterations=3`.

## State Keys

| Key | Type | Description |
|-----|------|-------------|
| `retrieved_docs[]` | `list[dict]` | Accumulated retrieved documents across rounds |
| `evidence_ledger{}` | `dict` | `doc_id → [claims]` mapping |
| `answer` | `str` | Final synthesized answer |
| `citations[]` | `list[dict]` | `(claim, doc_id)` pairs |
| `retrieval_round` | `int` | Current retrieval iteration (0-indexed) |
| `supported` | `bool` | Whether all claims are supported by evidence |

## Budget

| Budget | Value |
|--------|-------|
| `max_model_calls` | 5 |
| `max_tool_calls` | 8 |
| `max_iterations` | 3 |

## Tests

| Test | Description |
|------|-------------|
| `test_multi_hop_question` | 2-step retrieval across framework and database documents |
| `test_single_pass_baseline` | Single retrieval without iterative refinement |
| `test_unsupported_claim_rejected` | Query with no supporting documents |
| `test_citation_validation` | All citations trace to evidence ledger |
| `test_max_retrieval_rounds` | Loop limit enforced at 3 rounds |
| `test_state_keys_present` | All required state keys in output |
| `test_budget_enforcement` | Budget limits enforced in metrics |

## Usage

```bash
# Run default scenario
uv run python -m examples.15_agentic_rag.run

# Run specific scenario
uv run python -m examples.15_agentic_rag.run multi_hop
uv run python -m examples.15_agentic_rag.run single_pass_baseline

# Run tests
uv run pytest examples/15_agentic_rag/test_example.py -v
```

## Documents

The corpus contains 6 documents about a fictional company's tech stack:

- **doc_framework**: Python 3.12, FastAPI (migrated from Flask)
- **doc_database**: PostgreSQL 16 on AWS RDS, Redis caching
- **doc_deployment**: Docker, Kubernetes on EKS, GitHub Actions
- **doc_monitoring**: Prometheus, Grafana, PagerDuty
- **doc_team**: 45 engineers in 5 squads
- **doc_api_style**: RESTful, OpenAPI 3.1, OAuth 2.0
