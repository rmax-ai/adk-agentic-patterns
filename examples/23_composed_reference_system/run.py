#!/usr/bin/env python3
"""CLI runner for Pattern 23: Composed Production Reference System.

Usage:
    python run.py [--scenario SCENARIO] [--json] [--verbose]

Scenarios:
    read_only_inquiry   — Account inquiry: route → RAG → tool → answer (no approval)
    billing_dispute     — Billing dispute: route → RAG → tool → evaluate → answer
    refund_approved     — Refund request: route → RAG → tool → evaluate → approve → refund
    refund_rejected     — Refund request: route → RAG → tool → evaluate → reject
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure the package source is on the path BEFORE any package imports
_project_root = Path(__file__).resolve().parents[2]
_src_dir = _project_root / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

# Ensure this directory is on the path
_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))

from adk_patterns.config import Config, ExecutionMode

from agent import run


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pattern 23: Composed Production Reference System",
    )
    parser.add_argument(
        "--scenario",
        default="read_only_inquiry",
        choices=["read_only_inquiry", "billing_dispute", "refund_approved", "refund_rejected"],
        help="Test scenario to run (default: read_only_inquiry)",
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    config = Config(
        execution_mode=ExecutionMode.OFFLINE,
        verbose=args.verbose,
        json_output=args.json,
    )

    result = run(config=config, scenario=args.scenario)

    if args.json:
        print(json.dumps(result.model_dump(), indent=2, default=str))
        return

    print(f"Pattern: {result.pattern}")
    print(f"Scenario: {result.scenario}")
    print(f"Status: {result.status.value}")
    if result.failure_reason:
        print(f"Reason: {result.failure_reason}")

    if result.output:
        state = result.output.get("state", {})
        print(f"\nRoute: {state.get('route', 'N/A')}")
        print(f"Answer: {state.get('answer', 'N/A')[:200]}...")

        if state.get("evaluator_scores"):
            scores = state["evaluator_scores"]
            print(f"\nEvaluator Scores:")
            print(f"  Correctness:  {scores.get('correctness', 'N/A')}")
            print(f"  Completeness: {scores.get('completeness', 'N/A')}")
            print(f"  Safety:       {scores.get('safety', 'N/A')}")
            print(f"  Overall:      {scores.get('overall', 'N/A')}")
            print(f"  Passed:       {scores.get('passed', 'N/A')}")

        if state.get("approval"):
            approval = state["approval"]
            print(f"\nApproval Decision:")
            print(f"  Approved: {approval.get('approved', 'N/A')}")
            print(f"  Reviewer: {approval.get('reviewer', 'N/A')}")

        if state.get("refund_result"):
            refund = state["refund_result"]
            print(f"\nRefund Result:")
            print(f"  Success: {refund.get('success', 'N/A')}")
            print(f"  Refund ID: {refund.get('refund_id', 'N/A')}")
            if refund.get("error"):
                print(f"  Error: {refund['error']}")

        print(f"\nDocs retrieved: {len(state.get('docs', []))}")
        print(f"Tools executed: {len(state.get('tool_results', []))}")
        print(f"Event log entries: {result.output.get('event_log_count', 0)}")
        print(f"Trace spans: {len(result.output.get('spans', []))}")

    print(f"\nMetrics: {json.dumps(result.metrics, indent=2)}")


if __name__ == "__main__":
    main()
