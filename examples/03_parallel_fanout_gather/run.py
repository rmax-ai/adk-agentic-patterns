"""Entry point for Pattern 03: Parallel Fan-Out/Gather.

Usage:
    uv run python -m examples.03_parallel_fanout_gather.run
    uv run python -m examples.03_parallel_fanout_gather.run --scenario success
    uv run python -m examples.03_parallel_fanout_gather.run --scenario fail_fast
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
