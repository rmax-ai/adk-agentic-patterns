"""Entry point for Pattern 16: MCP Tool Gateway.

Usage:
    python examples/16_mcp_tool_gateway/run.py
    python examples/16_mcp_tool_gateway/run.py --scenario tool_invocation
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add both the example directory and the project src to path
_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))

_project_src = _example_dir.parent.parent / "src"
if str(_project_src) not in sys.path:
    sys.path.insert(0, str(_project_src))


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="MCP Tool Gateway Pattern")
    parser.add_argument(
        "--scenario",
        default="tool_discovery",
        help="Scenario key (default: tool_discovery)",
    )
    args = parser.parse_args()

    from agent import run

    result = run(scenario=args.scenario)
    print(f"Status: {result.status.value}")
    print(f"Output: {result.output}")
    print(f"Metrics: {result.metrics}")
    print(f"Audit events: {len(result.audit_events)}")


if __name__ == "__main__":
    main()
