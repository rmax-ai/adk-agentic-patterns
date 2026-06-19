"""Entry point for Pattern 11: Agent Handoff.

Usage:
    uv run python -m examples.11_agent_handoff.run
    uv run python -m examples.11_agent_handoff.run --scenario handoff_accepted
    uv run python -m examples.11_agent_handoff.run --scenario handoff_rejected
"""

from __future__ import annotations

import sys

from .agent import run


def main() -> None:
    args = sys.argv[1:]
    scenario = "default"

    for i, arg in enumerate(args):
        if arg == "--scenario" and i + 1 < len(args):
            scenario = args[i + 1]
        elif not arg.startswith("--") and scenario == "default":
            scenario = arg

    result = run(scenario=scenario)
    print(f"Status: {result.status.value}")
    print(f"Output: {result.output}")
    print(f"Metrics: {result.metrics}")


if __name__ == "__main__":
    main()
