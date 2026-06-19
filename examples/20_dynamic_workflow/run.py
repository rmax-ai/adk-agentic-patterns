"""Entry point for Pattern 20: Dynamic Workflow.

Usage:
    uv run python -m examples.20_dynamic_workflow.run
    uv run python -m examples.20_dynamic_workflow.run schema_violation
    uv run python -m examples.20_dynamic_workflow.run unknown
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add parent to path so we can import agent module
_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))

from agent import run  # noqa: E402


def main() -> None:
    scenario = sys.argv[1] if len(sys.argv) > 1 else "default"
    result = run(scenario=scenario)

    print(f"Status: {result.status.value}")
    print(f"Output: {result.output}")
    print(f"Metrics: {result.metrics}")
    print(f"Audit events: {len(result.audit_events)}")

    if result.failure_reason:
        print(f"Failure reason: {result.failure_reason}")


if __name__ == "__main__":
    main()
