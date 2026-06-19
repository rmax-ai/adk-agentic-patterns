"""Entry point for Pattern 12: Shared Workspace / Blackboard.

Usage:
    uv run python -m examples.12_shared_workspace.run
    uv run python -m examples.12_shared_workspace.run --scenario append_only
    uv run python -m examples.12_shared_workspace.run --scenario version_conflict
    uv run python -m examples.12_shared_workspace.run --scenario synthesizer_rejected
"""

from __future__ import annotations

import sys

from .agent import run


def main() -> None:
    scenario = sys.argv[1] if len(sys.argv) > 1 else "success"
    result = run(scenario=scenario)
    print(f"Pattern: {result.pattern}")
    print(f"Scenario: {result.scenario}")
    print(f"Status: {result.status.value}")
    print(f"Output: {result.output}")
    print(f"Metrics: {result.metrics}")
    if result.failure_reason:
        print(f"Failure reason: {result.failure_reason}")


if __name__ == "__main__":
    main()
