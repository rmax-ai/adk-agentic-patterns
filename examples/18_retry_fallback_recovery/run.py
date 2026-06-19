"""Entry point for Pattern 18: Retry Fallback Recovery.

Usage:
    uv run python -m examples.18_retry_fallback_recovery.run
    uv run python -m examples.18_retry_fallback_recovery.run success
    uv run python -m examples.18_retry_fallback_recovery.run transient_then_success
    uv run python -m examples.18_retry_fallback_recovery.run permanent_error
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add example directory to sys.path for intra-package imports
_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))

from agent import run  # noqa: E402


def main() -> None:
    scenario = sys.argv[1] if len(sys.argv) > 1 else "default"
    result = run(scenario=scenario)
    print(f"Status: {result.status.value}")
    print(f"Output: {result.output}")
    print(f"Metrics: {result.metrics}")
    print(f"Audit events: {len(result.audit_events)}")

    if result.output:
        state = result.output
        print(f"\nState summary:")
        print(f"  account_data: {state.get('account_data')}")
        print(f"  retry_count: {state.get('retry_count')}")
        print(f"  circuit_state: {state.get('circuit_state')}")
        print(f"  dead_letter count: {len(state.get('dead_letter', []))}")


if __name__ == "__main__":
    main()
