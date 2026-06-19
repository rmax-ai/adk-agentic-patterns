"""Pattern 15: Agentic RAG — multi-hop question answering with iterative retrieval.

Scenario: Answer multi-hop questions over a small local corpus.
The agent iteratively retrieves documents, builds an evidence ledger tracking
which docs support which claims, validates citations, and rejects unsupported
claims. A single-pass RAG baseline is included for comparison.

State keys:
  retrieved_docs[]       — accumulated retrieved documents across rounds
  evidence_ledger{}      — doc_id → list of claims supported by that doc
  answer                 — final synthesized answer
  citations[]            — list of (claim, doc_id) pairs
  retrieval_round        — current retrieval iteration (0-indexed)

Budget: max_model_calls=5, max_tool_calls=8, max_iterations=3
Max retrieval rounds: 3
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from adk_patterns.config import Config
from adk_patterns.contracts import ExecutionStatus, PatternRunResult, ToolInvocationRecord
from adk_patterns.models import (
    ScriptedModel,
    ModelResponse,
    TokenUsage,
    text_response,
    tool_call_response,
)
from adk_patterns.shared import RunContext, run_scope

# Add this directory to path so we can import sibling modules
_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))


# ---------------------------------------------------------------------------
# Document fixtures (small local corpus)
# ---------------------------------------------------------------------------

DOCUMENTS: list[dict[str, str]] = [
    {"doc_id": "doc_framework", "content": "Acme Corp uses Python 3.12 and FastAPI for their backend services. They migrated from Flask in early 2025."},
    {"doc_id": "doc_database", "content": "The primary data store for Acme Corp is PostgreSQL 16, deployed on AWS RDS. They also use Redis for caching."},
    {"doc_id": "doc_deployment", "content": "Acme Corp deploys all services using Docker containers orchestrated by Kubernetes on EKS. CI/CD is handled by GitHub Actions."},
    {"doc_id": "doc_monitoring", "content": "Monitoring infrastructure at Acme Corp uses Prometheus for metrics collection and Grafana for dashboards. PagerDuty handles alerting."},
    {"doc_id": "doc_team", "content": "The engineering team at Acme Corp consists of 45 engineers split into 5 squads: Platform, Backend, Frontend, Data, and ML."},
    {"doc_id": "doc_api_style", "content": "Acme Corp's API follows RESTful conventions with OpenAPI 3.1 specifications. They use OAuth 2.0 for authentication."},
]

# Predefined similarity scores for deterministic testing
PREDEFINED_SCORES: dict[str, dict[str, float]] = {
    "What framework and database does Acme Corp use?": {
        "doc_framework": 0.95,
        "doc_database": 0.92,
        "doc_deployment": 0.3,
    },
    "What database do they use?": {
        "doc_database": 0.98,
        "doc_framework": 0.2,
    },
    "single_pass": {
        "doc_framework": 0.95,
        "doc_database": 0.92,
    },
    "What ML framework does Acme Corp use?": {
        "doc_framework": 0.4,
        "doc_team": 0.3,
    },
    "__retrieve_more__": {
        "doc_framework": 0.9,
    },
    "__retrieve_more_2__": {
        "doc_database": 0.9,
    },
    "What monitoring tools does Acme Corp use?": {
        "doc_monitoring": 0.95,
    },
}


# ── Contracts ───────────────────────────────────────────────────────────────


class Citation(BaseModel):
    """A citation linking a claim to a supporting document."""

    claim: str = Field(description="The specific claim made")
    doc_id: str = Field(description="Document ID supporting this claim")


class EvidenceLedger(BaseModel):
    """Tracks which documents support which claims."""

    entries: dict[str, list[str]] = Field(
        default_factory=dict,
        description="doc_id → list of claims supported by that doc",
    )

    def add_claim(self, doc_id: str, claim: str) -> None:
        if doc_id not in self.entries:
            self.entries[doc_id] = []
        if claim not in self.entries[doc_id]:
            self.entries[doc_id].append(claim)

    def get_doc_ids(self) -> list[str]:
        return list(self.entries.keys())

    def get_all_claims(self) -> list[str]:
        all_claims: list[str] = []
        for claims in self.entries.values():
            all_claims.extend(claims)
        return all_claims


# ── Model response fixtures ───────────────────────────────────────────────


# Multi-hop scenario: first check decides more docs needed, second check says enough
R1_MULTI_HOP_CHECK = text_response(
    "RETRIEVE_MORE: What database do they use?",
    prompt_tokens=30, completion_tokens=10,
)
R2_MULTI_HOP_CHECK = text_response(
    "ENOUGH: Acme Corp uses Python 3.12/FastAPI (from doc_framework) and PostgreSQL on AWS RDS with Redis (from doc_database).",
    prompt_tokens=30, completion_tokens=20,
)
R3_MULTI_HOP_SYNTHESIZE = text_response(
    "CLAIM: Acme Corp uses Python 3.12 and FastAPI for backend services | SOURCE: doc_framework\n"
    "CLAIM: They migrated from Flask in early 2025 | SOURCE: doc_framework\n"
    "CLAIM: Primary data store is PostgreSQL 16 on AWS RDS | SOURCE: doc_database\n"
    "CLAIM: They also use Redis for caching | SOURCE: doc_database",
    prompt_tokens=50, completion_tokens=100,
)

# Single-pass baseline: directly synthesize
R1_BASELINE_SYNTHESIZE = text_response(
    "CLAIM: Acme Corp uses Python 3.12 and FastAPI | SOURCE: doc_framework\n"
    "CLAIM: Database is PostgreSQL 16 on AWS RDS | SOURCE: doc_database\n"
    "CLAIM: They use Redis for caching | SOURCE: doc_database",
    prompt_tokens=50, completion_tokens=60,
)

# Unsupported claim: answer with unsupported marker
R1_UNSUPPORTED_CHECK = text_response(
    "ENOUGH: I'll answer now.",
    prompt_tokens=20, completion_tokens=10,
)
R2_UNSUPPORTED_SYNTHESIZE = text_response(
    "CLAIM: Acme Corp might use TensorFlow or PyTorch for ML | SOURCE: UNSUPPORTED\n"
    "No documents mention ML frameworks used by Acme Corp.",
    prompt_tokens=40, completion_tokens=50,
)

# Citation validation: clear claim with source
R1_CITATION_MONITORING_CHECK = text_response(
    "ENOUGH: Acme Corp uses Prometheus, Grafana, and PagerDuty for monitoring.",
    prompt_tokens=20, completion_tokens=15,
)
R2_CITATION_MONITORING_SYNTHESIZE = text_response(
    "CLAIM: Acme Corp uses Prometheus for metrics collection | SOURCE: doc_monitoring\n"
    "CLAIM: Grafana is used for dashboards | SOURCE: doc_monitoring\n"
    "CLAIM: PagerDuty handles alerting | SOURCE: doc_monitoring",
    prompt_tokens=30, completion_tokens=70,
)

# Max retrieval rounds: always asks for more, exhausting 3 rounds
R1_EXHAUST_CHECK = text_response(
    "RETRIEVE_MORE: more docs",
    prompt_tokens=20, completion_tokens=5,
)
R2_EXHAUST_CHECK = text_response(
    "RETRIEVE_MORE: even more docs",
    prompt_tokens=20, completion_tokens=5,
)
R3_EXHAUST_CHECK = text_response(
    "RETRIEVE_MORE: still more docs",
    prompt_tokens=20, completion_tokens=5,
)
R4_EXHAUST_SYNTHESIZE = text_response(
    "CLAIM: Some claim from available documents | SOURCE: doc_framework\n"
    "CLAIM: Another claim from documents | SOURCE: doc_database",
    prompt_tokens=30, completion_tokens=50,
)


# ── Response sequences per scenario ─────────────────────────────────────────

SEQUENCES: dict[str, list[ModelResponse]] = {
    # Multi-hop: check → RETRIEVE_MORE → check → ENOUGH → synthesize
    "multi_hop": [
        R1_MULTI_HOP_CHECK,       # round 1: needs more docs
        R2_MULTI_HOP_CHECK,       # round 2: has enough -> synthesize
        R3_MULTI_HOP_SYNTHESIZE,  # round 2: synthesize answer
    ],
    # Single pass: synthesize directly (no retrieval check calls)
    "single_pass_baseline": [
        R1_BASELINE_SYNTHESIZE,   # synthesize answer immediately
    ],
    # Unsupported claim: check once → ENOUGH → synthesize with unsupported
    "unsupported_claim": [
        R1_UNSUPPORTED_CHECK,     # round 1: has enough
        R2_UNSUPPORTED_SYNTHESIZE,  # round 1: synthesize answer
    ],
    # Citation validation: check → ENOUGH → synthesize
    "citation_validation": [
        R1_CITATION_MONITORING_CHECK,     # round 1: has enough
        R2_CITATION_MONITORING_SYNTHESIZE,  # round 1: synthesize answer
    ],
    # Max retrieval rounds: 3x RETRIEVE_MORE, then synthesize
    "max_retrieval_rounds": [
        R1_EXHAUST_CHECK,    # round 1: needs more docs
        R2_EXHAUST_CHECK,    # round 2: needs more docs
        R3_EXHAUST_CHECK,    # round 3: needs more docs
        R4_EXHAUST_SYNTHESIZE,  # round 3: synthesize answer (forced)
    ],
}

# Default sequence (same as multi_hop)
SEQUENCES["default"] = SEQUENCES["multi_hop"]

# ── Queries per scenario ────────────────────────────────────────────────────

QUERIES: dict[str, str] = {
    "default": "What framework and database does Acme Corp use?",
    "multi_hop": "What framework and database does Acme Corp use?",
    "single_pass_baseline": "single_pass",
    "unsupported_claim": "What ML framework does Acme Corp use?",
    "citation_validation": "What monitoring tools does Acme Corp use?",
    "max_retrieval_rounds": "__retrieve_more__",
}


# ── Core Agent ──────────────────────────────────────────────────────────────


def _build_document_store() -> Any:
    """Create and populate a MockDocumentStore with fixture documents and predefined scores."""
    from adk_patterns.mocks.document_store import Document, MockDocumentStore

    store = MockDocumentStore()
    for doc_data in DOCUMENTS:
        store.insert(Document(
            doc_id=doc_data["doc_id"],
            content=doc_data["content"],
        ))

    for query, scores in PREDEFINED_SCORES.items():
        store.set_scores(query, scores)

    return store


def _retrieve_documents(
    store: Any,
    query: str,
    top_k: int = 3,
    min_score: float = 0.5,
) -> list[dict[str, Any]]:
    """Search the document store and return results as dicts."""
    results = store.search(query=query, top_k=top_k, min_score=min_score)
    return [
        {
            "doc_id": r.doc_id,
            "content": r.content,
            "score": r.score,
            "citation_id": getattr(r, "citation_id", f"cite:{r.doc_id}"),
        }
        for r in results
    ]


def _should_retrieve_more(
    model: ScriptedModel,
    ctx: RunContext,
    query: str,
    current_docs: list[dict[str, Any]],
    retrieval_round: int,
) -> bool:
    """Ask the model if more documents are needed.

    The model can request additional retrieval by returning a response with
    the text "RETRIEVE_MORE" in it. If the model returns any other text,
    retrieval stops and answer synthesis begins.
    """
    doc_summary = "\n".join(
        f"  [{d['doc_id']}] {d['content'][:120]}"
        for d in current_docs
    )

    prompt = (
        f"Query: {query}\n\n"
        f"Retrieved documents (round {retrieval_round + 1}):\n"
        f"{doc_summary}\n\n"
        f"Do you have enough information to answer this question?\n"
        f"Reply with 'RETRIEVE_MORE: <refined query>' if you need more documents.\n"
        f"Reply with 'ENOUGH: <answer>' if you can answer now."
    )

    ctx.record_model_call(tokens=50)
    ctx.audit("agent", "retrieval_check", resource=f"round_{retrieval_round}")

    response = model.invoke(
        system_instruction="You are a RAG assistant determining if more retrieval is needed.",
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.text or ""
    return text.startswith("RETRIEVE_MORE")


def _synthesize_answer(
    model: ScriptedModel,
    ctx: RunContext,
    query: str,
    retrieved_docs: list[dict[str, Any]],
    retrieval_round: int,
) -> dict[str, Any]:
    """Synthesize a final answer with citations and evidence ledger."""
    doc_text = "\n\n".join(
        f"[{d['doc_id']}] {d['content']}"
        for d in retrieved_docs
    )

    prompt = (
        f"Based on the following documents, answer the query: {query}\n\n"
        f"Documents:\n{doc_text}\n\n"
        "For each claim in your answer, cite the source document ID.\n"
        "Format your answer as:\n"
        "CLAIM: <claim text> | SOURCE: <doc_id>\n"
        "...\n\n"
        "If a claim cannot be supported by any document, note it as UNSUPPORTED."
    )

    ctx.record_model_call(tokens=100)
    ctx.audit("agent", "synthesize", resource=f"round_{retrieval_round}")

    response = model.invoke(
        system_instruction="You synthesize answers with citations from provided documents.",
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_answer_response(response.text or "", retrieved_docs)


def _parse_answer_response(
    text: str,
    retrieved_docs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Parse a model's answer text into structured form with ledgers and citations."""
    ledger = EvidenceLedger()
    citations: list[Citation] = []
    answer_parts: list[str] = []
    all_supported = True

    doc_map = {d["doc_id"]: d for d in retrieved_docs}

    for line in text.strip().split("\n"):
        line = line.strip()
        if line.startswith("CLAIM:"):
            # Parse claim and citation
            if "| SOURCE:" in line:
                parts = line.split("| SOURCE:")
                claim = parts[0].replace("CLAIM:", "").strip()
                source = parts[1].strip()
                if source.upper() == "UNSUPPORTED":
                    all_supported = False
                    answer_parts.append(f"{claim} (UNSUPPORTED)")
                elif source in doc_map:
                    ledger.add_claim(source, claim)
                    citations.append(Citation(claim=claim, doc_id=source))
                    answer_parts.append(claim)
                else:
                    all_supported = False
                    answer_parts.append(f"{claim} (UNSUPPORTED: source '{source}' not found)")
            else:
                claim = line.replace("CLAIM:", "").strip()
                all_supported = False
                answer_parts.append(f"{claim} (UNSUPPORTED)")
        elif line and not line.startswith("|") and not line.startswith("SOURCE:"):
            answer_parts.append(line)

    answer = " ".join(answer_parts) if answer_parts else text

    return {
        "answer": answer,
        "citations": [c.model_dump() for c in citations],
        "evidence_ledger": ledger.model_dump(),
        "supported": all_supported,
    }


# ── Agentic RAG Loop ────────────────────────────────────────────────────────


def run_agentic_rag(
    ctx: RunContext,
    model: ScriptedModel,
    query: str,
    document_store: Any,
    max_rounds: int = 3,
    top_k: int = 3,
    min_score: float = 0.5,
) -> dict[str, Any]:
    """Run the Agentic RAG loop with iterative retrieval and evidence tracking.

    Args:
        ctx: Run context for audit and budget tracking.
        model: ScriptedModel with pre-configured response sequence.
        query: The user's question.
        document_store: MockDocumentStore instance.
        max_rounds: Maximum retrieval iterations.
        top_k: Documents to retrieve per round.
        min_score: Minimum similarity score threshold.

    Returns:
        Dict with keys: retrieved_docs, evidence_ledger, answer, citations,
        retrieval_rounds, supported, termination_reason.
    """
    state: dict[str, Any] = {
        "retrieved_docs": [],
        "evidence_ledger": {},
        "answer": None,
        "citations": [],
        "retrieval_round": 0,
        "supported": True,
        "termination_reason": "unknown",
    }

    current_query = query

    for retrieval_round in range(max_rounds):
        # Check budgets
        budget_status = ctx.check_budget()
        if budget_status is not None:
            state["termination_reason"] = "budget_exhausted"
            ctx.mark_budget_exhausted()
            break

        ctx.record_iteration()
        state["retrieval_round"] = retrieval_round + 1

        # ── Step 1: Retrieve documents ──────────────────────────────────
        ctx.audit("agent", "retrieve", resource=f"round_{retrieval_round}")
        docs = _retrieve_documents(document_store, current_query, top_k=top_k, min_score=min_score)

        # Deduplicate
        existing_ids = {d["doc_id"] for d in state["retrieved_docs"]}
        for d in docs:
            if d["doc_id"] not in existing_ids:
                state["retrieved_docs"].append(d)
                existing_ids.add(d["doc_id"])

        ctx.record_tool_call(
            ToolInvocationRecord(
                tool_name="retrieve",
                validated_arguments={"query": current_query, "top_k": top_k},
                result_summary={"doc_count": len(docs)},
            )
        )

        # ── Step 2: Check if we need more documents ─────────────────────
        if retrieval_round < max_rounds - 1:
            needs_more = _should_retrieve_more(model, ctx, query, state["retrieved_docs"], retrieval_round)
            if needs_more:
                # Extract refined query from model response
                if model.invocations:
                    last_inv = model.invocations[-1]
                    if last_inv.response and last_inv.response.text:
                        text = last_inv.response.text
                        if "RETRIEVE_MORE:" in text:
                            refined = text.split("RETRIEVE_MORE:")[1].split("\n")[0].strip()
                            if refined:
                                current_query = refined
                ctx.audit("agent", "refine_query", resource=f"round_{retrieval_round}", metadata={"new_query": current_query})
                continue
            else:
                # Model says we have enough — synthesize answer
                state["termination_reason"] = "enough_information"
                break
        else:
            # Last round — synthesize answer regardless
            state["termination_reason"] = "max_rounds_reached"

    # ── Step 3: Synthesize final answer ────────────────────────────────
    if state["retrieved_docs"]:
        result = _synthesize_answer(model, ctx, query, state["retrieved_docs"], state["retrieval_round"])
        state["answer"] = result["answer"]
        state["citations"] = result["citations"]
        state["evidence_ledger"] = result["evidence_ledger"]
        state["supported"] = result["supported"]
    else:
        state["answer"] = "No relevant documents found."
        state["supported"] = False
        state["citations"] = []
        state["termination_reason"] = "no_documents"

    ctx.snapshot_state(state)
    return state


# ── Single-Pass Baseline ────────────────────────────────────────────────────


def run_single_pass_rag(
    ctx: RunContext,
    model: ScriptedModel,
    query: str,
    document_store: Any,
    top_k: int = 3,
) -> dict[str, Any]:
    """Single-pass RAG baseline — one retrieval, no iterative refinement.

    Used for comparison with the multi-hop agentic approach.
    """
    state: dict[str, Any] = {
        "retrieved_docs": [],
        "evidence_ledger": {},
        "answer": None,
        "citations": [],
        "retrieval_round": 1,
        "supported": True,
        "termination_reason": "single_pass",
    }

    ctx.record_iteration()
    ctx.audit("agent", "baseline_retrieve", resource="single_pass")

    docs = _retrieve_documents(document_store, query, top_k=top_k)
    state["retrieved_docs"] = docs

    ctx.record_tool_call(
        ToolInvocationRecord(
            tool_name="retrieve",
            validated_arguments={"query": query, "top_k": top_k},
            result_summary={"doc_count": len(docs)},
        )
    )

    if docs:
        result = _synthesize_answer(model, ctx, query, docs, 1)
        state["answer"] = result["answer"]
        state["citations"] = result["citations"]
        state["evidence_ledger"] = result["evidence_ledger"]
        state["supported"] = result["supported"]
    else:
        state["answer"] = "No relevant documents found."
        state["supported"] = False

    ctx.snapshot_state(state)
    return state


# ── Citation Validation ─────────────────────────────────────────────────────


def validate_citations(
    state: dict[str, Any],
) -> dict[str, Any]:
    """Validate that all citations reference documents in the evidence ledger.

    Returns validation result with any unsupported or mismatched citations.
    """
    ledger = state.get("evidence_ledger", {})
    citations = state.get("citations", [])

    ledger_entries = ledger.get("entries", {}) if isinstance(ledger, dict) else {}
    ledger_doc_ids = set(ledger_entries.keys()) if isinstance(ledger_entries, dict) else set()
    valid_citations: list[Citation] = []
    invalid_citations: list[dict[str, Any]] = []

    for c in citations:
        if isinstance(c, dict):
            claim = c.get("claim", "")
            doc_id = c.get("doc_id", "")
        else:
            claim = getattr(c, "claim", "")
            doc_id = getattr(c, "doc_id", "")

        if doc_id in ledger_doc_ids:
            valid_citations.append(Citation(claim=claim, doc_id=doc_id))
        else:
            invalid_citations.append({"claim": claim, "doc_id": doc_id, "reason": "not_in_ledger"})

    state["citation_validation"] = {
        "valid": [c.model_dump() for c in valid_citations],
        "invalid": invalid_citations,
        "all_valid": len(invalid_citations) == 0,
    }

    return state


# ── Entry Points ────────────────────────────────────────────────────────────


def run(config: Config | None = None, scenario: str = "default") -> PatternRunResult:
    """Entry point for CLI and tests.

    Args:
        config: Application configuration (uses defaults if None).
        scenario: Test scenario key.

    Returns:
        A PatternRunResult with status, output, metrics, and audit trail.
    """
    model = ScriptedModel()

    seq = SEQUENCES.get(scenario)
    if seq:
        model.set_response_sequence(seq)

    document_store = _build_document_store()
    query = QUERIES.get(scenario, "What framework and database does Acme Corp use?")

    with run_scope(
        "agentic-rag",
        scenario,
        max_model_calls=5,
        max_tool_calls=8,
        max_iterations=3,
    ) as ctx:
        if scenario == "single_pass_baseline":
            state = run_single_pass_rag(ctx, model, query, document_store)
        else:
            state = run_agentic_rag(ctx, model, query, document_store, max_rounds=3)
        ctx.output = state

    return ctx.to_result()


def main(config: Config | None = None, scenario: str = "default") -> PatternRunResult:
    """Standard entry point called by CLI."""
    return run(config=config, scenario=scenario)
