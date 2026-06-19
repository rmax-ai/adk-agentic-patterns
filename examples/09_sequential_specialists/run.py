"""Entry point for Pattern 09: Sequential Specialists.

Usage:
    uv run python -m examples.09_sequential_specialists.run
    uv run python -m examples.09_sequential_specialists.run valid_auto
    uv run python -m examples.09_sequential_specialists.run ineligible
    uv run python -m examples.09_sequential_specialists.run fraud_suspicious
"""

from __future__ import annotations

import sys
from pathlib import Path

_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))

from agent import run


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
