"""Pattern registry — the single source of truth for all pattern metadata.

The comparison matrix is generated from this registry, not maintained manually.
"""

from __future__ import annotations

from adk_patterns.contracts import PatternMetadata

# All patterns defined here. Each pattern example directory must register itself
# by adding an entry. The benchmark, CLI, and comparison matrix all read from this.

PATTERNS: dict[str, PatternMetadata] = {}


def register(pattern: PatternMetadata) -> PatternMetadata:
    """Register a pattern in the global registry."""
    PATTERNS[pattern.name] = pattern
    return pattern


def get(name: str) -> PatternMetadata | None:
    """Get a pattern by name."""
    return PATTERNS.get(name)


def list_all() -> list[PatternMetadata]:
    """List all registered patterns sorted by autonomy level."""
    return sorted(PATTERNS.values(), key=lambda p: p.autonomy_level)


# -- Pre-register all 23 patterns with metadata stubs --
# Phase 2: Foundational patterns
register(PatternMetadata(
    name="single-model-call",
    display_name="Single Structured Model Call",
    phase=2,
    description="Classify a support request into a typed category with one model invocation.",
    autonomy_level=0,
    determinism=10, adaptability=1, state_complexity=0, coordination_complexity=0,
    testability=10, failure_containment=10, security_isolation=10,
    latency="low", token_consumption="low",
    resumability=False, human_controllability=10, operational_burden=0,
    recommended_use_cases=["Classification", "Extraction", "Simple transformation"],
    reasons_not_to_use=["Multi-step reasoning", "Tool use required", "Dynamic decision-making"],
    related_patterns=["prompt-chaining"],
))

register(PatternMetadata(
    name="prompt-chaining",
    display_name="Prompt Chaining",
    phase=2,
    description="Transform a raw incident report through sequential stages with schema validation between each.",
    autonomy_level=1,
    determinism=8, adaptability=2, state_complexity=2, coordination_complexity=1,
    testability=9, failure_containment=8, security_isolation=9,
    latency="medium", token_consumption="medium",
    resumability=False, human_controllability=9, operational_burden=1,
    recommended_use_cases=["Document processing pipelines", "Multi-stage extraction", "Structured report generation"],
    reasons_not_to_use=["Independent steps", "Simple single-call tasks", "Non-linear flows"],
    related_patterns=["single-model-call", "sequential-specialists"],
))

register(PatternMetadata(
    name="router-specialist",
    display_name="Router-Specialist",
    phase=2,
    description="Route customer requests to billing, account, or technical specialists with typed routing verdicts.",
    autonomy_level=2,
    determinism=7, adaptability=4, state_complexity=3, coordination_complexity=2,
    testability=8, failure_containment=7, security_isolation=8,
    latency="medium", token_consumption="medium",
    resumability=False, human_controllability=8, operational_burden=2,
    recommended_use_cases=["Customer support triage", "Multi-domain Q&A", "Specialist dispatch"],
    reasons_not_to_use=["Single domain", "Fixed flow known in advance", "No specialist needed"],
    related_patterns=["parallel-fanout", "supervisor-worker"],
))

register(PatternMetadata(
    name="parallel-fanout",
    display_name="Parallel Fan-Out/Gather",
    phase=2,
    description="Evaluate a vendor simultaneously for security, legal, operational, and financial concerns.",
    autonomy_level=2,
    determinism=7, adaptability=3, state_complexity=4, coordination_complexity=3,
    testability=7, failure_containment=6, security_isolation=7,
    latency="low", token_consumption="high",
    resumability=False, human_controllability=7, operational_burden=2,
    recommended_use_cases=["Multi-perspective evaluation", "Independent parallel checks", "Vendor assessment"],
    reasons_not_to_use=["Sequential dependencies", "Shared mutable state", "Simple single-view tasks"],
    related_patterns=["router-specialist", "shared-workspace"],
))

register(PatternMetadata(
    name="tool-using-agent",
    display_name="Tool-Using Agent",
    phase=2,
    description="Inspect an order and answer its status using mocked inventory, shipment, and customer tools.",
    autonomy_level=3,
    determinism=6, adaptability=5, state_complexity=3, coordination_complexity=2,
    testability=7, failure_containment=7, security_isolation=6,
    latency="medium", token_consumption="medium",
    resumability=False, human_controllability=8, operational_burden=2,
    recommended_use_cases=["Read-only system queries", "Data aggregation across tools", "Status lookups"],
    reasons_not_to_use=["Write operations without approval", "No external data needed", "Simple queries"],
    related_patterns=["react-loop", "agentic-rag", "mcp-tool-gateway"],
))

# Phase 3: Iterative and adaptive patterns
register(PatternMetadata(
    name="react-loop",
    display_name="ReAct Agent Loop",
    phase=3,
    description="Diagnose a fictional service incident by querying metrics, logs, and deployment history.",
    autonomy_level=5,
    determinism=4, adaptability=7, state_complexity=5, coordination_complexity=3,
    testability=5, failure_containment=5, security_isolation=6,
    latency="high", token_consumption="high",
    resumability=False, human_controllability=5, operational_burden=4,
    recommended_use_cases=["Incident diagnosis", "Exploratory analysis", "Debugging workflows"],
    reasons_not_to_use=["Fixed procedure known", "Low latency required", "Deterministic path exists"],
    related_patterns=["tool-using-agent", "bounded-loop", "evaluator-optimizer"],
))

register(PatternMetadata(
    name="planner-executor",
    display_name="Planner-Executor",
    phase=3,
    description="Plan and execute a small conference setup — planner creates typed plan, executor runs scoped tools.",
    autonomy_level=6,
    determinism=3, adaptability=8, state_complexity=7, coordination_complexity=6,
    testability=4, failure_containment=4, security_isolation=7,
    latency="high", token_consumption="high",
    resumability=True, human_controllability=5, operational_burden=5,
    recommended_use_cases=["Complex multi-step tasks", "Conference/event planning", "Project execution"],
    reasons_not_to_use=["Simple tasks", "Fixed workflow", "No replanning needed"],
    related_patterns=["evaluator-optimizer", "dynamic-workflow", "durable-saga"],
))

register(PatternMetadata(
    name="evaluator-optimizer",
    display_name="Evaluator-Optimizer",
    phase=3,
    description="Generate a technical change proposal and iteratively improve it against a rubric.",
    autonomy_level=4,
    determinism=5, adaptability=6, state_complexity=4, coordination_complexity=3,
    testability=6, failure_containment=6, security_isolation=8,
    latency="high", token_consumption="high",
    resumability=False, human_controllability=7, operational_burden=3,
    recommended_use_cases=["Content refinement", "Code review", "Quality improvement loops"],
    reasons_not_to_use=["One-shot sufficient", "No quality rubric", "Real-time requirements"],
    related_patterns=["bounded-loop", "planner-executor"],
))

register(PatternMetadata(
    name="bounded-loop",
    display_name="Bounded Loop Agent",
    phase=3,
    description="Draft and validate a compliance report until all required sections are present.",
    autonomy_level=4,
    determinism=4, adaptability=6, state_complexity=4, coordination_complexity=2,
    testability=5, failure_containment=5, security_isolation=7,
    latency="high", token_consumption="high",
    resumability=False, human_controllability=6, operational_burden=3,
    recommended_use_cases=["Iterative refinement", "Compliance validation", "Quality gates"],
    reasons_not_to_use=["Single-pass tasks", "Deterministic verification sufficient"],
    related_patterns=["evaluator-optimizer", "react-loop"],
))

register(PatternMetadata(
    name="dynamic-workflow",
    display_name="Dynamic Workflow",
    phase=3,
    description="Process a data-quality incident where execution branches depend on discovered conditions.",
    autonomy_level=7,
    determinism=3, adaptability=9, state_complexity=6, coordination_complexity=5,
    testability=4, failure_containment=4, security_isolation=6,
    latency="medium", token_consumption="medium",
    resumability=True, human_controllability=4, operational_burden=5,
    recommended_use_cases=["Data quality pipelines", "Conditional workflows", "Investigation processes"],
    reasons_not_to_use=["Fixed flow", "Simple branching", "Overhead for linear tasks"],
    related_patterns=["planner-executor", "durable-saga"],
))

# Phase 4: Coordination patterns
register(PatternMetadata(
    name="sequential-specialists",
    display_name="Sequential Specialists",
    phase=4,
    description="Process an insurance claim through extraction, eligibility, fraud screening, and explanation.",
    autonomy_level=3,
    determinism=6, adaptability=4, state_complexity=5, coordination_complexity=3,
    testability=7, failure_containment=6, security_isolation=7,
    latency="medium", token_consumption="high",
    resumability=False, human_controllability=7, operational_burden=2,
    recommended_use_cases=["Document processing pipelines", "Claim processing", "Multi-stage review"],
    reasons_not_to_use=["Independent steps", "No ordering required", "Simple single-agent tasks"],
    related_patterns=["prompt-chaining", "supervisor-worker"],
))

register(PatternMetadata(
    name="supervisor-worker",
    display_name="Supervisor-Worker",
    phase=4,
    description="A supervisor decomposes a product-launch review into specialist tasks with a typed task ledger.",
    autonomy_level=6,
    determinism=3, adaptability=8, state_complexity=7, coordination_complexity=7,
    testability=4, failure_containment=4, security_isolation=6,
    latency="high", token_consumption="high",
    resumability=True, human_controllability=5, operational_burden=6,
    recommended_use_cases=["Complex decompositions", "Multi-specialist coordination", "Product reviews"],
    reasons_not_to_use=["Simple tasks", "Single specialist", "No coordination overhead justified"],
    related_patterns=["router-specialist", "shared-workspace", "planner-executor"],
))

register(PatternMetadata(
    name="agent-handoff",
    display_name="Agent Handoff",
    phase=4,
    description="Support agent transfers a conversation to a refund specialist with narrowed permissions.",
    autonomy_level=4,
    determinism=5, adaptability=5, state_complexity=3, coordination_complexity=4,
    testability=6, failure_containment=7, security_isolation=8,
    latency="medium", token_consumption="medium",
    resumability=False, human_controllability=7, operational_burden=3,
    recommended_use_cases=["Escalation workflows", "Specialist transfers", "Permission-scoped delegation"],
    reasons_not_to_use=["Single agent sufficient", "No permission boundaries", "Stateless interactions"],
    related_patterns=["router-specialist", "supervisor-worker"],
))

register(PatternMetadata(
    name="shared-workspace",
    display_name="Shared Workspace / Blackboard",
    phase=4,
    description="Multiple research workers contribute claims to an append-only shared evidence board.",
    autonomy_level=5,
    determinism=4, adaptability=6, state_complexity=8, coordination_complexity=8,
    testability=3, failure_containment=3, security_isolation=5,
    latency="high", token_consumption="high",
    resumability=False, human_controllability=4, operational_burden=7,
    recommended_use_cases=["Collaborative research", "Evidence gathering", "Multi-agent analysis"],
    reasons_not_to_use=["Simple coordination", "Single writer", "Low complexity tasks"],
    related_patterns=["parallel-fanout", "supervisor-worker"],
))

# Phase 5: Enterprise control patterns
register(PatternMetadata(
    name="human-approval-gate",
    display_name="Human Approval Gate",
    phase=5,
    description="Agent proposes a customer refund but cannot execute without human approval.",
    autonomy_level=3,
    determinism=6, adaptability=3, state_complexity=5, coordination_complexity=3,
    testability=6, failure_containment=8, security_isolation=9,
    latency="high", token_consumption="medium",
    resumability=True, human_controllability=10, operational_burden=4,
    recommended_use_cases=["Financial operations", "High-risk actions", "Compliance workflows"],
    reasons_not_to_use=["Low-risk read operations", "Fully automated systems", "No human-in-the-loop needed"],
    related_patterns=["guardrails-policy-gate", "durable-saga"],
))

register(PatternMetadata(
    name="memory-partitioning",
    display_name="Memory Partitioning",
    phase=5,
    description="Personal task assistant with working, session, episodic, and user-profile memory stores.",
    autonomy_level=4,
    determinism=5, adaptability=6, state_complexity=7, coordination_complexity=5,
    testability=5, failure_containment=6, security_isolation=7,
    latency="medium", token_consumption="medium",
    resumability=True, human_controllability=6, operational_burden=5,
    recommended_use_cases=["Personal assistants", "Long-running conversations", "Context-aware agents"],
    reasons_not_to_use=["Stateless tasks", "Single session", "No persistent context needed"],
    related_patterns=["agentic-rag", "shared-workspace"],
))

register(PatternMetadata(
    name="agentic-rag",
    display_name="Agentic RAG",
    phase=5,
    description="Answer multi-hop questions over a small local corpus with iterative query refinement.",
    autonomy_level=4,
    determinism=5, adaptability=6, state_complexity=5, coordination_complexity=3,
    testability=6, failure_containment=6, security_isolation=8,
    latency="medium", token_consumption="medium",
    resumability=False, human_controllability=7, operational_burden=4,
    recommended_use_cases=["Multi-hop QA", "Document-grounded answers", "Research assistance"],
    reasons_not_to_use=["Single-hop queries", "No document grounding needed", "Simple lookup"],
    related_patterns=["tool-using-agent", "react-loop", "memory-partitioning"],
))

register(PatternMetadata(
    name="mcp-tool-gateway",
    display_name="MCP Tool Gateway",
    phase=5,
    description="Expose mocked ticketing and knowledge-search through a local MCP server consumed by ADK.",
    autonomy_level=3,
    determinism=6, adaptability=4, state_complexity=4, coordination_complexity=5,
    testability=5, failure_containment=6, security_isolation=7,
    latency="medium", token_consumption="medium",
    resumability=False, human_controllability=7, operational_burden=5,
    recommended_use_cases=["Tool interoperability", "MCP integration", "Multi-framework tool sharing"],
    reasons_not_to_use=["No MCP needed", "Direct tool integration simpler", "No cross-framework tools"],
    related_patterns=["tool-using-agent", "guardrails-policy-gate"],
))

register(PatternMetadata(
    name="guardrails-policy-gate",
    display_name="Guardrails and Policy Gate",
    phase=5,
    description="Classify and block unsafe payment requests with pre-model, pre-tool, and post-tool policies.",
    autonomy_level=2,
    determinism=8, adaptability=3, state_complexity=3, coordination_complexity=3,
    testability=9, failure_containment=9, security_isolation=10,
    latency="low", token_consumption="low",
    resumability=False, human_controllability=10, operational_burden=3,
    recommended_use_cases=["Safety filtering", "Authorization enforcement", "Compliance gates"],
    reasons_not_to_use=["No risk of harm", "Fully trusted inputs", "No external side effects"],
    related_patterns=["human-approval-gate", "retry-fallback-recovery"],
))

register(PatternMetadata(
    name="retry-fallback-recovery",
    display_name="Retry, Fallback, and Recovery",
    phase=5,
    description="Retrieve account data from an unreliable mocked service with backoff, circuit breaker, and dead letter.",
    autonomy_level=1,
    determinism=8, adaptability=4, state_complexity=3, coordination_complexity=2,
    testability=9, failure_containment=9, security_isolation=8,
    latency="medium", token_consumption="low",
    resumability=False, human_controllability=9, operational_burden=2,
    recommended_use_cases=["Unreliable service calls", "Network resilience", "Graceful degradation"],
    reasons_not_to_use=["Guaranteed services", "No fallback acceptable", "Real-time hard deadlines"],
    related_patterns=["durable-saga", "guardrails-policy-gate"],
))

register(PatternMetadata(
    name="durable-saga",
    display_name="Durable SAGA Workflow",
    phase=5,
    description="Mocked travel booking with append-only event log, checkpoints, compensating actions, and crash recovery.",
    autonomy_level=5,
    determinism=5, adaptability=5, state_complexity=8, coordination_complexity=7,
    testability=5, failure_containment=8, security_isolation=7,
    latency="high", token_consumption="high",
    resumability=True, human_controllability=6, operational_burden=7,
    recommended_use_cases=["Multi-service transactions", "Booking systems", "Order fulfillment"],
    reasons_not_to_use=["Atomic operations", "No compensation needed", "Simple single-service calls"],
    related_patterns=["retry-fallback-recovery", "human-approval-gate", "dynamic-workflow"],
))

register(PatternMetadata(
    name="budget-aware-routing",
    display_name="Budget-Aware Model Routing",
    phase=5,
    description="Route simple, medium, and complex requests to fake model tiers with cost-aware escalation.",
    autonomy_level=2,
    determinism=7, adaptability=5, state_complexity=3, coordination_complexity=3,
    testability=8, failure_containment=7, security_isolation=8,
    latency="low", token_consumption="low",
    resumability=False, human_controllability=8, operational_burden=3,
    recommended_use_cases=["Cost optimization", "Tiered model serving", "Complexity-based routing"],
    reasons_not_to_use=["Uniform complexity", "Single model tier", "No cost constraints"],
    related_patterns=["router-specialist", "evaluator-optimizer"],
))

register(PatternMetadata(
    name="observability-evaluation",
    display_name="Observability and Evaluation",
    phase=5,
    description="Instrument a multi-step workflow with traces, spans, and deterministic evaluators.",
    autonomy_level=1,
    determinism=9, adaptability=2, state_complexity=4, coordination_complexity=3,
    testability=10, failure_containment=8, security_isolation=9,
    latency="low", token_consumption="low",
    resumability=False, human_controllability=10, operational_burden=3,
    recommended_use_cases=["Workflow monitoring", "Quality assurance", "Production observability"],
    reasons_not_to_use=["No observability needed", "Single-step workflows", "Ad-hoc exploration"],
    related_patterns=["composed-reference-system"],
))

# Phase 6: Composition
register(PatternMetadata(
    name="composed-reference-system",
    display_name="Composed Production Reference System",
    phase=6,
    description="Regulated customer-support workflow composing policy gates, routing, RAG, tools, evaluation, approval, and durability.",
    autonomy_level=5,
    determinism=5, adaptability=7, state_complexity=9, coordination_complexity=9,
    testability=4, failure_containment=7, security_isolation=8,
    latency="high", token_consumption="high",
    resumability=True, human_controllability=7, operational_burden=8,
    recommended_use_cases=["Production reference", "Regulated workflows", "Full-system demonstration"],
    reasons_not_to_use=["Learning individual patterns", "Simple applications", "Overhead not justified"],
    related_patterns=[],
))
