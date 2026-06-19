"""Entry point for Pattern 02: Router-Specialist.

Usage:
    uv run python -m examples.02_router_specialist.run
    uv run python -m examples.02_router_specialist.run --scenario billing_route
    uv run python -m examples.02_router_specialist.run --rule
"""

from __future__ import annotations

import sys

from .agent import run


def main() -> None:
    args = sys.argv[1:]
    scenario = "default"
    use_rule_router = False

    for i, arg in enumerate(args):
        if arg == "--rule":
            use_rule_router = True
        elif arg == "--scenario" and i + 1 < len(args):
            scenario = args[i + 1]
        elif not arg.startswith("--") and scenario == "default":
            scenario = arg

    result = run(scenario=scenario, use_rule_router=use_rule_router)
    print(f"Status: {result.status.value}")
    print(f"Output: {result.output}")
    print(f"Metrics: {result.metrics}")


if __name__ == "__main__":
    main()
