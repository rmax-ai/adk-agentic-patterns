"""Scoped worker tool implementations for Pattern 10: Supervisor-Worker.

Each worker has its own isolated tool set. Workers cannot use tools
belonging to other workers. The permission check prevents cross-worker
task modification.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Ensure this example directory is on sys.path for absolute imports
_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))

from mocks import MockComplianceWorker, MockLaunchWorker, MockMarketWorker, MockTechWorker  # noqa: E402


# ---------------------------------------------------------------------------
# Market worker tools
# ---------------------------------------------------------------------------


def tool_market_analyze(market_worker: MockMarketWorker, product: str) -> dict[str, Any]:
    """Analyze market for a product.

    Args:
        product: Product name.

    Returns:
        Market analysis results.
    """
    return market_worker.analyze_market(product)


def tool_pricing_review(market_worker: MockMarketWorker, product: str, price: float) -> dict[str, Any]:
    """Review proposed pricing.

    Args:
        product: Product name.
        price: Proposed price.

    Returns:
        Pricing review results.
    """
    return market_worker.review_pricing(product, price)


def tool_competitor_intel(market_worker: MockMarketWorker, product: str) -> dict[str, Any]:
    """Gather competitor intelligence.

    Args:
        product: Product name.

    Returns:
        Competitor intel results.
    """
    return market_worker.competitor_intel(product)


# ---------------------------------------------------------------------------
# Tech worker tools
# ---------------------------------------------------------------------------


def tool_tech_review(tech_worker: MockTechWorker, product: str) -> dict[str, Any]:
    """Perform technical review.

    Args:
        product: Product name.

    Returns:
        Technical review results.
    """
    return tech_worker.review_technical(product)


def tool_security_audit(tech_worker: MockTechWorker, product: str) -> dict[str, Any]:
    """Perform security audit.

    Args:
        product: Product name.

    Returns:
        Security audit results.
    """
    return tech_worker.security_audit(product)


def tool_performance_benchmark(tech_worker: MockTechWorker, product: str) -> dict[str, Any]:
    """Run performance benchmarks.

    Args:
        product: Product name.

    Returns:
        Benchmark results.
    """
    return tech_worker.performance_benchmark(product)


# ---------------------------------------------------------------------------
# Compliance worker tools
# ---------------------------------------------------------------------------


def tool_compliance_check(compliance_worker: MockComplianceWorker, product: str, region: str = "global") -> dict[str, Any]:
    """Check compliance requirements.

    Args:
        product: Product name.
        region: Target region (default: global).

    Returns:
        Compliance check results.
    """
    return compliance_worker.check_compliance(product, region)


def tool_regulatory_review(compliance_worker: MockComplianceWorker, product: str) -> dict[str, Any]:
    """Perform regulatory review.

    Args:
        product: Product name.

    Returns:
        Regulatory review results.
    """
    return compliance_worker.regulatory_review(product)


def tool_data_privacy(compliance_worker: MockComplianceWorker, product: str) -> dict[str, Any]:
    """Review data privacy.

    Args:
        product: Product name.

    Returns:
        Data privacy results.
    """
    return compliance_worker.data_privacy_review(product)


# ---------------------------------------------------------------------------
# Launch worker tools
# ---------------------------------------------------------------------------


def tool_assess_readiness(launch_worker: MockLaunchWorker, product: str) -> dict[str, Any]:
    """Assess launch readiness.

    Args:
        product: Product name.

    Returns:
        Readiness assessment.
    """
    return launch_worker.assess_readiness(product)


def tool_go_to_market(launch_worker: MockLaunchWorker, product: str) -> dict[str, Any]:
    """Create go-to-market plan summary.

    Args:
        product: Product name.

    Returns:
        GTM plan results.
    """
    return launch_worker.go_to_market(product)


# ---------------------------------------------------------------------------
# Permission enforcement
# ---------------------------------------------------------------------------


# Maps worker_id -> set of allowed tool names
WORKER_TOOL_ALLOWLIST: dict[str, set[str]] = {
    "worker_market": {"market_analyze", "pricing_review", "competitor_intel"},
    "worker_tech": {"tech_review", "security_audit", "performance_benchmark"},
    "worker_compliance": {"compliance_check", "regulatory_review", "data_privacy"},
    "worker_launch": {"assess_readiness", "go_to_market"},
}

# Maps task_id -> worker_id
TASK_ASSIGNMENTS: dict[str, str] = {
    "task-market": "worker_market",
    "task-tech": "worker_tech",
    "task-compliance": "worker_compliance",
    "task-launch": "worker_launch",
}


def check_worker_can_modify_task(worker_id: str, task_id: str) -> bool:
    """Check if a worker is allowed to modify a specific task.

    Workers can only modify tasks assigned to them.
    """
    expected_worker = TASK_ASSIGNMENTS.get(task_id)
    return expected_worker == worker_id


def check_worker_tool_allowed(worker_id: str, tool_name: str) -> bool:
    """Check if a worker is allowed to use a specific tool.

    Workers can only use tools in their allowlist.
    """
    allowed = WORKER_TOOL_ALLOWLIST.get(worker_id, set())
    return tool_name in allowed


def update_task_assignment(task_id: str, worker_id: str) -> None:
    """Update a task assignment (used during supervisor decomposition)."""
    TASK_ASSIGNMENTS[task_id] = worker_id


def clear_assignments() -> None:
    """Clear all task assignments (for test isolation)."""
    TASK_ASSIGNMENTS.clear()


# ---------------------------------------------------------------------------
# Tool registries (scoped per worker)
# ---------------------------------------------------------------------------

MarketToolRegistry = dict[str, Any]
TechToolRegistry = dict[str, Any]
ComplianceToolRegistry = dict[str, Any]
LaunchToolRegistry = dict[str, Any]

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "market_analyze",
        "description": "Analyze market conditions for a product",
        "parameters": {"product": {"type": "string", "description": "Product name"}},
        "worker": "worker_market",
    },
    {
        "name": "pricing_review",
        "description": "Review proposed pricing for a product",
        "parameters": {
            "product": {"type": "string", "description": "Product name"},
            "price": {"type": "number", "description": "Proposed price"},
        },
        "worker": "worker_market",
    },
    {
        "name": "competitor_intel",
        "description": "Gather competitor intelligence",
        "parameters": {"product": {"type": "string", "description": "Product name"}},
        "worker": "worker_market",
    },
    {
        "name": "tech_review",
        "description": "Perform technical review of a product",
        "parameters": {"product": {"type": "string", "description": "Product name"}},
        "worker": "worker_tech",
    },
    {
        "name": "security_audit",
        "description": "Perform security audit",
        "parameters": {"product": {"type": "string", "description": "Product name"}},
        "worker": "worker_tech",
    },
    {
        "name": "performance_benchmark",
        "description": "Run performance benchmarks",
        "parameters": {"product": {"type": "string", "description": "Product name"}},
        "worker": "worker_tech",
    },
    {
        "name": "compliance_check",
        "description": "Check compliance requirements for a product",
        "parameters": {
            "product": {"type": "string", "description": "Product name"},
            "region": {"type": "string", "description": "Target region (default: global)"},
        },
        "worker": "worker_compliance",
    },
    {
        "name": "regulatory_review",
        "description": "Perform regulatory review",
        "parameters": {"product": {"type": "string", "description": "Product name"}},
        "worker": "worker_compliance",
    },
    {
        "name": "data_privacy",
        "description": "Review data privacy aspects",
        "parameters": {"product": {"type": "string", "description": "Product name"}},
        "worker": "worker_compliance",
    },
    {
        "name": "assess_readiness",
        "description": "Assess launch readiness for a product",
        "parameters": {"product": {"type": "string", "description": "Product name"}},
        "worker": "worker_launch",
    },
    {
        "name": "go_to_market",
        "description": "Create go-to-market plan summary",
        "parameters": {"product": {"type": "string", "description": "Product name"}},
        "worker": "worker_launch",
    },
]


def create_worker_tools(
    market_worker: MockMarketWorker,
    tech_worker: MockTechWorker,
    compliance_worker: MockComplianceWorker,
    launch_worker: MockLaunchWorker,
) -> dict[str, dict[str, Any]]:
    """Create scoped tool registries for each worker.

    Returns a dict mapping worker_id -> {tool_name: callable}.
    """
    return {
        "worker_market": {
            "market_analyze": lambda product: tool_market_analyze(market_worker, product),
            "pricing_review": lambda product, price: tool_pricing_review(market_worker, product, price),
            "competitor_intel": lambda product: tool_competitor_intel(market_worker, product),
        },
        "worker_tech": {
            "tech_review": lambda product: tool_tech_review(tech_worker, product),
            "security_audit": lambda product: tool_security_audit(tech_worker, product),
            "performance_benchmark": lambda product: tool_performance_benchmark(tech_worker, product),
        },
        "worker_compliance": {
            "compliance_check": lambda product, region="global": tool_compliance_check(
                compliance_worker, product, region
            ),
            "regulatory_review": lambda product: tool_regulatory_review(compliance_worker, product),
            "data_privacy": lambda product: tool_data_privacy(compliance_worker, product),
        },
        "worker_launch": {
            "assess_readiness": lambda product: tool_assess_readiness(launch_worker, product),
            "go_to_market": lambda product: tool_go_to_market(launch_worker, product),
        },
    }
