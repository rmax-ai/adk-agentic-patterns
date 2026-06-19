"""Entry point for Pattern 01: Prompt Chaining.

Usage:
    uv run python -m examples.01_prompt_chaining.run
    uv run python -m examples.01_prompt_chaining.run --scenario security_breach
    uv run python -m examples.01_prompt_chaining.run --scenario malformed_facts
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

    if result.failure_reason:
        print(f"Failure reason: {result.failure_reason}")


if __name__ == "__main__":
    main()
