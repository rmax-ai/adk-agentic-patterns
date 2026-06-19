#!/usr/bin/env python3
"""Verify all examples run correctly and optionally generate benchmark data.

Usage:
    uv run python scripts/verify_examples.py
    uv run python scripts/verify_examples.py --benchmark
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = PROJECT_ROOT / "examples"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))


def verify_examples(benchmark: bool = False) -> dict[str, dict]:
    """Run all example tests and collect results."""
    results = {}
    pattern_dirs = sorted(EXAMPLES_DIR.glob("*"))

    for pattern_dir in pattern_dirs:
        if not pattern_dir.is_dir():
            continue
        pattern_name = pattern_dir.name
        test_file = pattern_dir / "test_example.py"
        if not test_file.exists():
            print(f"  SKIP {pattern_name}: no test_example.py")
            continue

        import subprocess
        start = time.monotonic()
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(test_file), "-q", "--tb=short"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        elapsed = time.monotonic() - start

        status = "PASS" if result.returncode == 0 else "FAIL"
        print(f"  {status} {pattern_name} ({elapsed:.1f}s)")

        results[pattern_name] = {
            "status": status,
            "elapsed_ms": elapsed * 1000,
            "stdout": result.stdout[-500:] if result.stdout else "",
            "stderr": result.stderr[-500:] if result.stderr else "",
        }

    return results


def generate_benchmark(results: dict) -> None:
    """Generate benchmark artifacts."""
    ARTIFACTS_DIR.mkdir(exist_ok=True)

    benchmark = {
        "patterns": len(results),
        "passed": sum(1 for r in results.values() if r["status"] == "PASS"),
        "failed": sum(1 for r in results.values() if r["status"] == "FAIL"),
        "total_elapsed_ms": sum(r["elapsed_ms"] for r in results.values()),
        "results": results,
    }

    benchmark_path = ARTIFACTS_DIR / "pattern-benchmark.json"
    benchmark_path.write_text(json.dumps(benchmark, indent=2))
    print(f"\nBenchmark written to {benchmark_path}")
    print(f"  Patterns: {benchmark['patterns']}")
    print(f"  Passed: {benchmark['passed']}")
    print(f"  Failed: {benchmark['failed']}")
    print(f"  Total time: {benchmark['total_elapsed_ms'] / 1000:.1f}s")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", action="store_true")
    args = parser.parse_args()

    print("Verifying all examples...")
    results = verify_examples(benchmark=args.benchmark)

    if args.benchmark:
        generate_benchmark(results)

    failed = sum(1 for r in results.values() if r["status"] == "FAIL")
    if failed:
        print(f"\n{failed} pattern(s) failed.")
        sys.exit(1)
    else:
        print(f"\nAll {len(results)} patterns passed.")


if __name__ == "__main__":
    main()
