"""Entry point for Pattern 14: Memory Partitioning.

Usage:
    uv run python -m examples.14_memory_partitioning.run
    uv run python -m examples.14_memory_partitioning.run session
    uv run python -m examples.14_memory_partitioning.run profile
"""

from __future__ import annotations

import json
import sys

from adk_patterns.models import ScriptedModel, structured_response

from .agent import run_memory_agent
from .fixtures import (
    EPISODIC_MEMORY_RESPONSES,
    POISONING_FIXTURES,
    PROFILE_FIXTURES,
    SESSION_MEMORY_RESPONSES,
    STALE_FIXTURES,
    WORKING_MEMORY_RESPONSES,
)


def run(scenario: str = "default") -> dict:
    """Run the memory partitioning pattern with a given scenario."""
    model = ScriptedModel()

    # Register all fixtures for deterministic responses
    for key, entry in WORKING_MEMORY_RESPONSES.items():
        if isinstance(entry, dict):
            response = structured_response(entry)
        else:
            response = structured_response(entry.model_dump())
        model.register_fixture(key, response)

    for key, entry in SESSION_MEMORY_RESPONSES.items():
        response = structured_response(entry.model_dump())
        model.register_fixture(key, response)

    for key, entry in EPISODIC_MEMORY_RESPONSES.items():
        response = structured_response(entry.model_dump())
        model.register_fixture(key, response)

    for key, profile in PROFILE_FIXTURES.items():
        response = structured_response(profile.model_dump())
        model.register_fixture(key, response)

    for key, entry in POISONING_FIXTURES.items():
        response = structured_response(entry.model_dump())
        model.register_fixture(key, response)

    for key, entry in STALE_FIXTURES.items():
        response = structured_response(entry.model_dump())
        model.register_fixture(key, response)

    from adk_patterns.shared import run_scope

    with run_scope(
        "memory-partitioning",
        scenario,
        max_model_calls=3,
        max_tool_calls=5,
    ) as ctx:
        result = run_memory_agent(ctx, model, operation=scenario)

    return {
        "pattern": result.pattern,
        "scenario": result.scenario,
        "status": result.status.value,
        "output": result.output,
        "metrics": result.metrics,
        "failure_reason": result.failure_reason,
    }


def main() -> None:
    scenario = sys.argv[1] if len(sys.argv) > 1 else "default"
    result = run(scenario=scenario)

    print(f"Pattern: {result['pattern']}")
    print(f"Scenario: {result['scenario']}")
    print(f"Status: {result['status']}")
    if result["output"]:
        output = result["output"]
        print(f"Operation: {output.get('operation', 'N/A')}")
        print(f"Details: {json.dumps(output, indent=2, default=str)}")
    print(f"Metrics: {result['metrics']}")
    if result["failure_reason"]:
        print(f"Failure reason: {result['failure_reason']}")


if __name__ == "__main__":
    main()
