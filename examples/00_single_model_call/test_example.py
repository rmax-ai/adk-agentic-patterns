"""Tests for Pattern 00: Single Structured Model Call."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Example directories starting with digits aren't valid Python packages.
# Add parent to path so we can import from them.
_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))

from agent import run  # noqa: E402

from adk_patterns.contracts import ExecutionStatus


def test_success_billing() -> None:
    """Happy path: classify a billing issue."""
    result = run(scenario="billing_issue")
    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output["category"] == "billing"
    assert result.output["confidence"] > 0.5
    assert result.metrics["model_calls"] == 1
    assert result.metrics["tool_calls"] == 0
    assert result.metrics["iterations"] == 0


def test_success_account() -> None:
    """Classify an account issue."""
    result = run(scenario="account_issue")
    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output["category"] == "account"


def test_success_technical() -> None:
    """Classify a technical issue."""
    result = run(scenario="technical_issue")
    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output["category"] == "technical"


def test_low_confidence_ambiguous() -> None:
    """Ambiguous query gets low confidence."""
    result = run(scenario="ambiguous")
    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output["category"] == "general"
    assert result.output["confidence"] < 0.6


def test_single_model_call_only() -> None:
    """Verify exactly one model call — no tools, no loops."""
    result = run(scenario="billing_issue")
    assert result.metrics["model_calls"] == 1
    assert result.metrics["tool_calls"] == 0
    assert result.metrics["iterations"] == 0


def test_audit_events_present() -> None:
    """Audit events are recorded."""
    result = run(scenario="billing_issue")
    assert len(result.audit_events) >= 2  # model_call + model_response
    assert any(e.action == "model_call" for e in result.audit_events)
    assert any(e.action == "model_response" for e in result.audit_events)
