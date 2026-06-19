"""Entry point for Pattern 22: Observability and Evaluation.

Usage:
    uv run python -m examples.22_observability_and_evaluation.run
    uv run python -m examples.22_observability_and_evaluation.run success
    uv run python -m examples.22_observability_and_evaluation.run failure
"""

from __future__ import annotations

import json
import sys

from .agent import run


def main() -> None:
    scenario = sys.argv[1] if len(sys.argv) > 1 else "success"
    result = run(scenario=scenario)

    print(f"Status: {result['status']}")
    print(f"Output: {json.dumps(result['output'], indent=2)}")
    print(f"Evaluation results: {json.dumps(result['evaluation_results'], indent=2)}")
    print(f"Synthetic metrics: {json.dumps(result['synthetic_metrics'], indent=2)}")

    if result.get("trace"):
        spans = result["trace"].get("spans", [])
        print(f"\nTrace spans ({len(spans)}):")
        for s in spans:
            parent = (s.get("parent_span_id") or "none")[:8]
            print(f"  [{s['kind']:>18}] {s['name']:<30} "
                  f"id={s['span_id'][:8]} parent={parent} "
                  f"status={s['status']} dur={s['duration_ms']:.1f}ms")


if __name__ == "__main__":
    main()
