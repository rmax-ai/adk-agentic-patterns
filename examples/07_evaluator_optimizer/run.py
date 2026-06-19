"""Entry point for Pattern 07: Evaluator-Optimizer.

Usage:
    uv run python -m examples.07_evaluator_optimizer.run
    uv run python -m examples.07_evaluator_optimizer.run converge
"""

from __future__ import annotations

import sys

from .agent import run


def main() -> None:
    scenario = sys.argv[1] if len(sys.argv) > 1 else "default"
    result = run(scenario=scenario)
    print(f"Pattern: {result.pattern}")
    print(f"Scenario: {result.scenario}")
    print(f"Status: {result.status.value}")
    if result.output:
        output = result.output
        print(f"Output status: {output.get('status', 'unknown')}")
        print(f"Iterations: {output.get('iterations', 0)}")
        if "scores" in output:
            scores = output["scores"]
            if isinstance(scores, dict):
                print(f"Overall score: {scores.get('overall', 'N/A')}")
    print(f"Metrics: {result.metrics}")
    if result.failure_reason:
        print(f"Failure reason: {result.failure_reason}")


if __name__ == "__main__":
    main()
