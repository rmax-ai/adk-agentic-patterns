"""Tests for Pattern 17: Guardrails Policy Gate.

Covers:
- Safe payment request allowed through all guardrails
- Unsafe request blocked by pre-model keyword filter
- Prompt injection detected and blocked pre-model
- Tool blocked before execution by pre-tool authorization
- Tool output caught after execution by post-tool output policy
- Write operation denied on degradation (fail-closed)
- Read operation allowed on degradation (fail-open)
"""

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

from adk_patterns.contracts import ExecutionStatus  # noqa: E402


# ---------------------------------------------------------------------------
# Allow safe request — all guardrails pass
# ---------------------------------------------------------------------------


def test_allow_safe_request() -> None:
    """Safe payment request passes all guardrail layers and executes."""
    result = run(scenario="allow_safe_request")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output

    # Pre-model policy should allow
    verdicts = state.get("policy_verdicts", [])
    pre_model = [v for v in verdicts if v["phase"] == "pre_model"]
    assert len(pre_model) > 0
    assert pre_model[0]["verdict"] == "allow"

    # No blocked requests
    assert len(state.get("blocked_requests", [])) == 0

    # Tool should have succeeded
    tool_results = state.get("tool_results", {})
    assert "process_payment" in tool_results
    assert "error" not in tool_results["process_payment"]

    # Final answer present
    assert len(state.get("final_answer", "")) > 0

    # Budget should be respected (max_model_calls=2)
    assert result.metrics["model_calls"] <= 2
    assert result.metrics["tool_calls"] <= 3


# ---------------------------------------------------------------------------
# Block unsafe request — keyword filter catches before model
# ---------------------------------------------------------------------------


def test_block_unsafe_request() -> None:
    """Unsafe request with 'ignore all rules' blocked by pre-model keyword filter."""
    result = run(scenario="block_unsafe_request")

    assert result.status == ExecutionStatus.REJECTED
    assert result.output is not None

    state = result.output

    # Should have blocked requests
    blocked = state.get("blocked_requests", [])
    assert len(blocked) > 0

    # Pre-model verdict should be deny
    verdicts = state.get("policy_verdicts", [])
    pre_model = [v for v in verdicts if v["phase"] == "pre_model"]
    assert len(pre_model) > 0
    assert pre_model[0]["verdict"] == "deny"

    # No tool should have been called
    assert len(state.get("tool_results", {})) == 0
    assert state.get("final_answer", "") == ""

    # No model or tool calls consumed
    assert result.metrics["model_calls"] == 0
    assert result.metrics["tool_calls"] == 0


# ---------------------------------------------------------------------------
# Prompt injection blocked
# ---------------------------------------------------------------------------


def test_prompt_injection_blocked() -> None:
    """Prompt injection attempt blocked by pre-model policy."""
    result = run(scenario="prompt_injection_blocked")

    assert result.status == ExecutionStatus.REJECTED
    assert result.output is not None

    state = result.output

    # Should have blocked requests
    blocked = state.get("blocked_requests", [])
    assert len(blocked) > 0

    # Pre-model verdict should be deny
    verdicts = state.get("policy_verdicts", [])
    pre_model = [v for v in verdicts if v["phase"] == "pre_model"]
    assert len(pre_model) > 0
    assert pre_model[0]["verdict"] == "deny"

    # The reason_code should relate to prompt injection
    assert "injection" in pre_model[0]["reason_code"] or "keyword" in pre_model[0]["reason_code"]

    # No tool or model calls consumed
    assert result.metrics["model_calls"] == 0
    assert result.metrics["tool_calls"] == 0


# ---------------------------------------------------------------------------
# Pre-tool authorization — tool blocked before execution
# ---------------------------------------------------------------------------


def test_pre_tool_authorization() -> None:
    """Tool blocked before execution by pre-tool authorization policy."""
    result = run(scenario="pre_tool_authorization")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output

    # Pre-model should still allow
    verdicts = state.get("policy_verdicts", [])
    pre_model = [v for v in verdicts if v["phase"] == "pre_model"]
    assert len(pre_model) > 0
    assert pre_model[0]["verdict"] == "allow"

    # Tool should have been blocked
    tool_results = state.get("tool_results", {})
    refund_result = tool_results.get("refund_payment", {})
    assert "error" in refund_result
    assert "AuthorizationDenied" in refund_result.get("error_type", "")
    assert refund_result.get("policy_verdict") == "deny"
    assert refund_result.get("reason_code") == "unauthorized"

    # Blocked requests should include this
    blocked = state.get("blocked_requests", [])
    assert len(blocked) > 0
    assert any(b.get("tool") == "refund_payment" for b in blocked)

    # Final answer present
    assert len(state.get("final_answer", "")) > 0


# ---------------------------------------------------------------------------
# Post-tool output policy — bad output caught after tool returns
# ---------------------------------------------------------------------------


def test_post_tool_output_policy() -> None:
    """Tool output caught by post-tool output policy after execution."""
    result = run(scenario="post_tool_output_policy")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output

    # Pre-model should allow
    verdicts = state.get("policy_verdicts", [])
    pre_model = [v for v in verdicts if v["phase"] == "pre_model"]
    assert len(pre_model) > 0
    assert pre_model[0]["verdict"] == "allow"

    # Tool should have been executed but output blocked
    tool_results = state.get("tool_results", {})
    history_result = tool_results.get("view_payment_history", {})
    assert "error" in history_result
    assert "OutputPolicyBlocked" in history_result.get("error_type", "")
    assert history_result.get("policy_verdict") == "block"
    assert history_result.get("scrubbed") is True

    # Final answer present
    assert len(state.get("final_answer", "")) > 0


# ---------------------------------------------------------------------------
# Fail-closed write — write ops denied on degradation
# ---------------------------------------------------------------------------


def test_fail_closed_write() -> None:
    """Write operation denied on system degradation (fail-closed)."""
    result = run(scenario="fail_closed_write")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output

    # Degraded flag should be set
    assert state.get("degraded") is True

    # Tool should have been blocked by pre-tool auth with fail_closed_write
    tool_results = state.get("tool_results", {})
    payment_result = tool_results.get("process_payment", {})
    assert "error" in payment_result
    assert "AuthorizationDenied" in payment_result.get("error_type", "")
    assert "fail_closed_write" in payment_result.get("reason_code", "")

    # Blocked requests should include this
    blocked = state.get("blocked_requests", [])
    assert len(blocked) > 0
    assert any(b.get("reason") == "fail_closed_write" for b in blocked)

    # Final answer present
    assert len(state.get("final_answer", "")) > 0


# ---------------------------------------------------------------------------
# Fail-open read — safe read allowed on degradation
# ---------------------------------------------------------------------------


def test_fail_open_read() -> None:
    """Read operation allowed on system degradation (fail-open)."""
    result = run(scenario="fail_open_read")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output is not None

    state = result.output

    # Degraded flag should be set
    assert state.get("degraded") is True

    # Tool should have succeeded despite degradation (fail-open for reads)
    tool_results = state.get("tool_results", {})
    status_result = tool_results.get("get_payment_status", {})
    assert "error" not in status_result
    assert status_result.get("status") == "completed"

    # No blocked requests for this tool
    blocked = state.get("blocked_requests", [])
    payment_blocked = [b for b in blocked if b.get("tool") == "get_payment_status"]
    assert len(payment_blocked) == 0

    # Final answer present
    assert len(state.get("final_answer", "")) > 0
