"""Entry point for Pattern 00: Single Model Call.

Usage:
    uv run python -m examples.00_single_model_call.run
    uv run python -m examples.00_single_model_call.run --scenario billing_issue
"""

from __future__ import annotations

import sys

from .agent import run


def main() -> None:
    scenario = sys.argv[1] if len(sys.argv) > 1 else "default"
    result = run(scenario=scenario)
    print(f"Status: {result.status.value}")
    print(f"Output: {result.output}")
    print(f"Metrics: {result.metrics}")


if __name__ == "__main__":
    main()
