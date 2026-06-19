"""Entry point for Pattern 19: Durable SAGA.

Usage:
    uv run python -m examples.19_durable_saga.run
    uv run python -m examples.19_durable_saga.run success
    uv run python -m examples.19_durable_saga.run crash_after_payment
"""

from __future__ import annotations

import sys

from .agent import run


def main() -> None:
    scenario = sys.argv[1] if len(sys.argv) > 1 else "default"
    result = run(scenario=scenario)

    print(f"Status: {result.status.value}")
    print(f"Saga status: {result.output.get('saga_status', 'unknown')}")
    print(f"Steps completed: {[k for k, v in result.output.get('checkpoints', {}).items() if v.get('status') == 'completed']}")
    print(f"Final answer: {result.output.get('final_answer', 'N/A')}")
    print(f"Metrics: {result.metrics}")

    if result.failure_reason:
        print(f"Failure reason: {result.failure_reason}")


if __name__ == "__main__":
    main()
