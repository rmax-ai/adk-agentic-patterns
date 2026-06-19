"""Tests for Pattern 22: Observability and Evaluation.

Verifies:
- Trace structure (root span with child spans)
- Model call spans recorded with durations
- Tool call spans with tool_name attribute
- Evaluator: task completion
- Evaluator: maximum steps compliance
- Evaluator: schema validity
- Evaluator: forbidden tool usage
- Evaluator: state ownership violations
- Synthetic token tracking in span attributes
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Example directories starting with digits aren't valid Python packages.
_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))

from agent import run, evaluate_state_ownership  # noqa: E402
from adk_patterns.telemetry import (  # noqa: E402
    InMemoryExporter,
    Trace,
    Span,
    evaluate_task_completion,
    evaluate_maximum_steps,
    evaluate_schema_validity,
    evaluate_forbidden_tool_usage,
)


# ── Helper: build a basic trace ───────────────────────────────────────────


def _make_success_trace() -> Trace:
    """Build a minimal well-formed success trace for evaluator tests."""
    exporter = InMemoryExporter()
    trace = exporter.create_trace()

    root = trace.start_span("workflow", kind="INTERNAL")
    root.finish("OK")

    mc = trace.start_span("classify", kind="MODEL_CALL", parent_span_id=root.span_id)
    mc.attributes["prompt_tokens"] = 15
    mc.attributes["completion_tokens"] = 5
    mc.attributes["total_tokens"] = 20
    mc.finish("OK")

    rt = trace.start_span("route", kind="ROUTING", parent_span_id=root.span_id)
    rt.finish("OK")

    vl = trace.start_span("validate", kind="VALIDATION", parent_span_id=root.span_id)
    vl.finish("OK")

    tc = trace.start_span("lookup", kind="TOOL_CALL", parent_span_id=root.span_id)
    tc.attributes["tool_name"] = "lookup_tool"
    tc.attributes["arguments"] = {"query": "weather", "type": "weather"}
    tc.attributes["citation"] = "weather-api-v2"
    tc.attributes["source"] = "openweather"
    tc.finish("OK")

    mc2 = trace.start_span("answer", kind="MODEL_CALL", parent_span_id=root.span_id)
    mc2.attributes["prompt_tokens"] = 20
    mc2.attributes["completion_tokens"] = 30
    mc2.attributes["total_tokens"] = 50
    mc2.finish("OK")

    vl2 = trace.start_span("validate_answer", kind="VALIDATION", parent_span_id=root.span_id)
    vl2.finish("OK")

    return trace


def _make_forbidden_trace() -> Trace:
    """Build a trace with a forbidden tool call."""
    trace = _make_success_trace()
    # Add a forbidden tool span
    root_id = trace.spans[0].span_id
    fb = trace.start_span("exec_shell", kind="TOOL_CALL", parent_span_id=root_id)
    fb.attributes["tool_name"] = "exec_shell"
    fb.finish("ERROR")
    return trace


def _make_state_violation_trace() -> Trace:
    """Build a trace with state key violations."""
    trace = _make_success_trace()
    root_id = trace.spans[0].span_id
    vs = trace.start_span("unauthorized_write", kind="INTERNAL", parent_span_id=root_id)
    vs.add_event("state_transition", {"state_key": "disallowed_key__secret", "value": "hacked"})
    vs.finish("OK")
    return trace


# ── Trace structure tests ─────────────────────────────────────────────────


class TestTraceStructure:
    """Trace has root span with child spans."""

    def test_trace_structure(self) -> None:
        result = run(scenario="success")
        trace = result["trace"]

        assert "trace_id" in trace
        assert len(trace["trace_id"]) > 0

        spans = trace["spans"]
        assert len(spans) > 0, "Trace must have at least one span"

        # Find root span (parent_span_id is None)
        root_spans = [s for s in spans if s.get("parent_span_id") is None]
        assert len(root_spans) >= 1, "Trace must have a root span"

        root_id = root_spans[0]["span_id"]
        child_spans = [s for s in spans if s.get("parent_span_id") == root_id]
        assert len(child_spans) >= 1, "Root span must have child spans"

        # Verify span kinds present
        kinds = {s["kind"] for s in spans}
        assert "INTERNAL" in kinds
        assert "MODEL_CALL" in kinds
        assert "TOOL_CALL" in kinds or "ROUTING" in kinds or "VALIDATION" in kinds


# ── Model call spans ──────────────────────────────────────────────────────


class TestModelCallSpans:
    """Model call spans recorded with durations."""

    def test_model_call_spans(self) -> None:
        result = run(scenario="success")
        spans = result["trace"]["spans"]

        model_spans = [s for s in spans if s["kind"] == "MODEL_CALL"]
        assert len(model_spans) >= 2, "Should have at least 2 model call spans"

        for span in model_spans:
            assert span["duration_ms"] >= 0, "Duration must be non-negative"
            assert span["status"] == "OK"


# ── Tool call spans ───────────────────────────────────────────────────────


class TestToolCallSpans:
    """Tool call spans with tool_name attribute."""

    def test_tool_call_spans(self) -> None:
        result = run(scenario="success")
        spans = result["trace"]["spans"]

        tool_spans = [s for s in spans if s["kind"] == "TOOL_CALL"]
        assert len(tool_spans) >= 1, "Should have at least 1 tool call span"

        for span in tool_spans:
            assert "tool_name" in span["attributes"], (
                f"Tool call span missing tool_name: {span}"
            )
            assert len(span["attributes"]["tool_name"]) > 0


# ── Evaluator: task completion ────────────────────────────────────────────


class TestEvaluatorTaskCompletion:
    """Traces evaluated, completion=True."""

    def test_evaluator_task_completion(self) -> None:
        trace = _make_success_trace()
        result = evaluate_task_completion(trace)
        assert result["metric"] == "task_completion"
        assert result["passed"] is True


# ── Evaluator: maximum steps ──────────────────────────────────────────────


class TestEvaluatorMaximumSteps:
    """Step budget compliance check."""

    def test_evaluator_maximum_steps(self) -> None:
        trace = _make_success_trace()
        result = evaluate_maximum_steps(trace, max_steps=5)
        assert result["metric"] == "maximum_steps"
        assert result["passed"] is True

    def test_evaluator_maximum_steps_exceeded(self) -> None:
        """Verify that exceeding max steps fails."""
        trace = _make_success_trace()
        # Use max_steps=1 which should fail since we have >1 model + tool calls
        result = evaluate_maximum_steps(trace, max_steps=1)
        assert result["metric"] == "maximum_steps"
        assert result["passed"] is False


# ── Evaluator: schema validity ────────────────────────────────────────────


class TestEvaluatorSchemaValidity:
    """Validation spans OK."""

    def test_evaluator_schema_validity(self) -> None:
        trace = _make_success_trace()
        result = evaluate_schema_validity(trace)
        assert result["metric"] == "schema_validity"
        assert result["passed"] is True


# ── Evaluator: forbidden tool usage ───────────────────────────────────────


class TestEvaluatorForbiddenToolUsage:
    """Forbidden tools detected."""

    def test_evaluator_forbidden_tool_usage_passes(self) -> None:
        """No forbidden tools -> passes."""
        trace = _make_success_trace()
        result = evaluate_forbidden_tool_usage(trace, forbidden=["exec_shell", "delete_tool"])
        assert result["metric"] == "forbidden_tool_usage"
        assert result["passed"] is True
        assert "violations" not in result["details"] or result["details"] == "none"

    def test_evaluator_forbidden_tool_usage_detected(self) -> None:
        """Forbidden tool detected -> fails."""
        trace = _make_forbidden_trace()
        result = evaluate_forbidden_tool_usage(trace, forbidden=["exec_shell", "delete_tool"])
        assert result["metric"] == "forbidden_tool_usage"
        assert result["passed"] is False
        assert "exec_shell" in result["details"]


# ── Evaluator: state ownership ────────────────────────────────────────────


class TestEvaluatorStateOwnership:
    """State key violations detected."""

    def test_evaluator_state_ownership_passes(self) -> None:
        """No state violations -> passes."""
        trace = _make_success_trace()
        allowed = {
            "MODEL_CALL": ["classification", "tool_request", "final_answer"],
            "TOOL_CALL": ["tool_result"],
            "ROUTING": ["selected_tool"],
            "VALIDATION": [],
            "INTERNAL": ["workflow_status"],
        }
        result = evaluate_state_ownership(trace, allowed_keys=allowed)
        assert result["metric"] == "state_ownership"
        assert result["passed"] is True

    def test_evaluator_state_ownership_violation(self) -> None:
        """State key violation detected -> fails."""
        trace = _make_state_violation_trace()
        allowed = {
            "MODEL_CALL": ["classification", "tool_request", "final_answer"],
            "TOOL_CALL": ["tool_result"],
            "ROUTING": ["selected_tool"],
            "VALIDATION": [],
            "INTERNAL": ["workflow_status"],
        }
        result = evaluate_state_ownership(trace, allowed_keys=allowed)
        assert result["metric"] == "state_ownership"
        assert result["passed"] is False, (
            f"Expected failure but got: {result}"
        )
        assert "disallowed_key__secret" in result["details"]

    def test_state_ownership_in_agent_run_success(self) -> None:
        """Success scenario: no state violations in workflow."""
        result = run(scenario="success")
        evals = result["evaluation_results"]
        assert "state_ownership" in evals
        assert evals["state_ownership"]["passed"] is True

    def test_state_ownership_in_agent_run_violation(self) -> None:
        """State violation scenario: violations detected."""
        result = run(scenario="state_violation")
        evals = result["evaluation_results"]
        assert "state_ownership" in evals
        assert evals["state_ownership"]["passed"] is False


# ── Synthetic token tracking ──────────────────────────────────────────────


class TestSyntheticTokenTracking:
    """Token counts in span attributes."""

    def test_synthetic_token_tracking(self) -> None:
        result = run(scenario="success")
        spans = result["trace"]["spans"]

        model_spans = [s for s in spans if s["kind"] == "MODEL_CALL"]
        assert len(model_spans) >= 1

        token_attrs = ["prompt_tokens", "completion_tokens", "total_tokens"]
        has_tokens = any(
            all(a in s.get("attributes", {}) for a in token_attrs)
            for s in model_spans
        )
        assert has_tokens, (
            f"No model span has all token attributes: {token_attrs}"
        )

        # Verify synthetic metrics are present
        metrics = result["synthetic_metrics"]
        assert metrics["total_prompt_tokens"] > 0
        assert metrics["total_completion_tokens"] > 0
        assert metrics["total_tokens"] > 0
        assert metrics["total_tokens"] == (
            metrics["total_prompt_tokens"] + metrics["total_completion_tokens"]
        )

    def test_synthetic_tokens_in_metrics(self) -> None:
        result = run(scenario="success")
        metrics = result["synthetic_metrics"]
        assert metrics["model_call_count"] >= 2
        assert metrics["tool_call_count"] >= 1


# ── Integration: full pipeline produces trace and evaluations ─────────────


class TestFullPipeline:
    """End-to-end checks that the workflow produces expected outputs."""

    def test_success_scenario(self) -> None:
        result = run(scenario="success")
        assert result["status"] == "succeeded"
        assert result["output"]["success"] is True
        assert len(result["output"]["answer"]) > 0

        # All evaluators ran
        evals = result["evaluation_results"]
        assert "task_completion" in evals
        assert "maximum_steps" in evals
        assert "schema_validity" in evals
        assert "forbidden_tool_usage" in evals
        assert "state_ownership" in evals
        assert "argument_schema_alignment" in evals
        assert "citation_correctness" in evals

    def test_failure_scenario(self) -> None:
        """Empty request leads to empty answer but workflow still completes."""
        result = run(scenario="failure")
        # classification may be empty but workflow still runs
        assert "trace" in result
        assert "evaluation_results" in result

    def test_forbidden_tool_scenario(self) -> None:
        result = run(scenario="forbidden_tool")
        evals = result["evaluation_results"]
        assert evals["forbidden_tool_usage"]["passed"] is False
