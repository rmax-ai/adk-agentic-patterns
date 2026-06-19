"""CLI for the ADK Agentic Patterns reference repository.

Commands:
    uv run adk-patterns list
    uv run adk-patterns describe <pattern>
    uv run adk-patterns run <pattern> [--scenario <name>]
    uv run adk-patterns run-all
    uv run adk-patterns compare <pattern-a> <pattern-b>
    uv run adk-patterns matrix
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from pathlib import Path
from typing import Any

from adk_patterns.config import Config
from adk_patterns.registry import PATTERNS, list_all


def cmd_list(config: Config) -> int:
    """List all registered patterns."""
    patterns = list_all()
    if config.json_output:
        data = [
            {
                "name": p.name,
                "display_name": p.display_name,
                "phase": p.phase,
                "autonomy_level": p.autonomy_level,
                "description": p.description,
            }
            for p in patterns
        ]
        print(json.dumps(data, indent=2))
    else:
        for p in patterns:
            print(f"  {p.name:<30} [phase {p.phase}] L{p.autonomy_level} — {p.display_name}")
    return 0


def cmd_describe(config: Config, pattern_name: str) -> int:
    """Describe a specific pattern in detail."""
    pattern = PATTERNS.get(pattern_name)
    if pattern is None:
        print(f"Unknown pattern: {pattern_name}", file=sys.stderr)
        return 1

    if config.json_output:
        print(json.dumps(pattern.model_dump(), indent=2, default=str))
    else:
        print(f"\n  {pattern.display_name} ({pattern.name})")
        print(f"  Phase: {pattern.phase}  |  Autonomy Level: {pattern.autonomy_level}/10")
        print(f"  {pattern.description}\n")
        print(f"  Determinism: {pattern.determinism}/10")
        print(f"  Adaptability: {pattern.adaptability}/10")
        print(f"  State Complexity: {pattern.state_complexity}/10")
        print(f"  Coordination: {pattern.coordination_complexity}/10")
        print(f"  Testability: {pattern.testability}/10")
        print(f"  Latency: {pattern.latency}  |  Tokens: {pattern.token_consumption}")
        print(f"  Resumable: {pattern.resumability}")
        print(f"\n  ✓ Use for: {', '.join(pattern.recommended_use_cases)}")
        print(f"  ✗ Avoid for: {', '.join(pattern.reasons_not_to_use)}")
        print(f"  Related: {', '.join(pattern.related_patterns) if pattern.related_patterns else 'none'}")
    return 0


def cmd_run(
    config: Config,
    pattern_name: str,
    scenario: str = "default",
    execution_mode: str | None = None,
) -> int:
    """Run a specific pattern."""
    if execution_mode:
        config.execution_mode = execution_mode  # type: ignore[assignment]

    if pattern_name not in PATTERNS:
        print(f"Unknown pattern: {pattern_name}", file=sys.stderr)
        return 1

    try:
        module = importlib.import_module(f"examples.{pattern_name.replace('-', '_')}.run")
    except ImportError as e:
        print(f"Cannot load pattern '{pattern_name}': {e}", file=sys.stderr)
        print(f"Pattern may not be implemented yet.", file=sys.stderr)
        return 1

    if not hasattr(module, "main"):
        print(f"Pattern '{pattern_name}' has no main() entry point.", file=sys.stderr)
        return 1

    start = time.monotonic()
    result = module.main(config=config, scenario=scenario)  # type: ignore[call-arg]
    elapsed = time.monotonic() - start

    if config.json_output:
        output = result.model_dump() if hasattr(result, "model_dump") else {"result": str(result)}
        output["wall_clock_ms"] = elapsed * 1000
        print(json.dumps(output, indent=2, default=str))
    else:
        status = getattr(result, "status", "?")
        print(f"\n  Pattern: {pattern_name}  |  Scenario: {scenario}  |  Status: {status}")
        print(f"  Mode: {config.execution_mode.value}  |  Wall time: {elapsed:.2f}s")

        if hasattr(result, "metrics"):
            m: dict[str, Any] = result.metrics  # type: ignore[union-attr]
            print(f"  Model calls: {m.get('model_calls', '?')}  |  Tool calls: {m.get('tool_calls', '?')}")
            print(f"  Iterations: {m.get('iterations', '?')}  |  Tokens: {m.get('synthetic_tokens', '?')}")

        failure_reason: str | None = getattr(result, "failure_reason", None)  # type: ignore[union-attr]
        if failure_reason:
            print(f"  Failure: {failure_reason}")
    return 0


def cmd_compare(config: Config, pattern_a: str, pattern_b: str) -> int:
    """Compare two patterns side by side."""
    a = PATTERNS.get(pattern_a)
    b = PATTERNS.get(pattern_b)
    if not a:
        print(f"Unknown pattern: {pattern_a}", file=sys.stderr)
        return 1
    if not b:
        print(f"Unknown pattern: {pattern_b}", file=sys.stderr)
        return 1

    dims = [
        ("Determinism", "determinism"),
        ("Adaptability", "adaptability"),
        ("State Complexity", "state_complexity"),
        ("Coordination", "coordination_complexity"),
        ("Testability", "testability"),
        ("Failure Containment", "failure_containment"),
        ("Security Isolation", "security_isolation"),
        ("Human Controllability", "human_controllability"),
        ("Operational Burden", "operational_burden"),
    ]

    if config.json_output:
        print(json.dumps({
            "pattern_a": a.model_dump(),
            "pattern_b": b.model_dump(),
        }, indent=2, default=str))
    else:
        print(f"\n  {'Dimension':<25} {a.display_name:<20} {b.display_name:<20}")
        print(f"  {'-'*25} {'-'*20} {'-'*20}")
        for label, attr in dims:
            va = getattr(a, attr)
            vb = getattr(b, attr)
            print(f"  {label:<25} {str(va):<20} {str(vb):<20}")
        print(f"\n  {a.display_name}: {a.latency} latency, {a.token_consumption} tokens")
        print(f"  {b.display_name}: {b.latency} latency, {b.token_consumption} tokens")
    return 0


def cmd_matrix(config: Config) -> int:
    """Generate the pattern comparison matrix."""
    patterns = list_all()
    dims = [
        "determinism", "adaptability", "state_complexity",
        "coordination_complexity", "testability", "failure_containment",
        "security_isolation", "human_controllability", "operational_burden",
    ]

    if config.json_output:
        rows = []
        for p in patterns:
            row = {"name": p.name, "display_name": p.display_name}
            for d in dims:
                row[d] = getattr(p, d)
            row["latency"] = p.latency
            row["token_consumption"] = p.token_consumption
            row["resumable"] = p.resumability
            rows.append(row)
        print(json.dumps(rows, indent=2))
    else:
        print(f"\n  {'Pattern':<30} {'Det':>3} {'Adp':>3} {'StC':>3} {'CoC':>3} {'Tst':>3} {'FaC':>3} {'Sec':>3} {'HuC':>3} {'OpB':>3}")
        print(f"  {'-'*30} {'---'*9}")
        for p in patterns:
            print(
                f"  {p.name:<30} "
                f"{p.determinism:>3} {p.adaptability:>3} {p.state_complexity:>3} "
                f"{p.coordination_complexity:>3} {p.testability:>3} "
                f"{p.failure_containment:>3} {p.security_isolation:>3} "
                f"{p.human_controllability:>3} {p.operational_burden:>3}"
            )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="adk-patterns",
        description="ADK Agentic Design Patterns — executable reference catalogue",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="List all patterns")

    desc = sub.add_parser("describe", help="Describe a pattern")
    desc.add_argument("pattern", help="Pattern name")

    run = sub.add_parser("run", help="Run a pattern")
    run.add_argument("pattern", help="Pattern name")
    run.add_argument("--scenario", default="default", help="Scenario name")
    run.add_argument("--execution-mode", choices=["offline", "live"], help="Execution mode override")

    sub.add_parser("run-all", help="Run all patterns")

    cmp = sub.add_parser("compare", help="Compare two patterns")
    cmp.add_argument("pattern_a", help="First pattern")
    cmp.add_argument("pattern_b", help="Second pattern")

    sub.add_parser("matrix", help="Generate comparison matrix")

    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--trace", action="store_true", help="Enable tracing")

    args = parser.parse_args()
    config = Config.from_env()
    config.json_output = args.json
    config.verbose = args.verbose
    config.trace = args.trace

    if args.command == "list":
        return cmd_list(config)
    elif args.command == "describe":
        return cmd_describe(config, args.pattern)
    elif args.command == "run":
        return cmd_run(config, args.pattern, args.scenario, args.execution_mode)
    elif args.command == "run-all":
        print("run-all not yet implemented", file=sys.stderr)
        return 1
    elif args.command == "compare":
        return cmd_compare(config, args.pattern_a, args.pattern_b)
    elif args.command == "matrix":
        return cmd_matrix(config)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
