"""Entry point for Pattern 17: Guardrails Policy Gate.

Usage:
    uv run python -m examples.17_guardrails_policy_gate.run
    uv run python -m examples.17_guardrails_policy_gate.run allow_safe_request
    uv run python -m examples.17_guardrails_policy_gate.run block_unsafe_request
    uv run python -m examples.17_guardrails_policy_gate.run prompt_injection_blocked
    uv run python -m examples.17_guardrails_policy_gate.run pre_tool_authorization
    uv run python -m examples.17_guardrails_policy_gate.run post_tool_output_policy
    uv run python -m examples.17_guardrails_policy_gate.run fail_closed_write
    uv run python -m examples.17_guardrails_policy_gate.run fail_open_read
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
