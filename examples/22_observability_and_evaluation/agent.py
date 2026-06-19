"""Pattern 22: Observability and Evaluation.

Instrument a multi-step agent workflow (classify → tool_lookup → answer)
and evaluate recorded traces using deterministic evaluators.

Trace ID, span hierarchy (root, model_call, tool_call, routing, validation, state_transition).
Synthetic token count, tool latency, task completion result.
Cost-per-success, groundedness score, schema-validity rate, failure category.
Lightweight in-memory OpenTelemetry-like exporter (adk_patterns.telemetry).
Deterministic evaluators for: task completion, argument schema alignment,
citation correctness, maximum-step compliance, forbidden-tool usage,
state ownership violations.
"""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path
from typing import Any

from adk_patterns.contracts import ExecutionStatus, PatternRunResult
from adk_patterns.models import (
    ScriptedModel,
    text_response,
    tool_call_response,
)
from adk_patterns.telemetry import (
    InMemoryExporter,
    Trace,
    evaluate_task_completion,
    evaluate_maximum_steps,
    evaluate_schema_validity,
    evaluate_forbidden_tool_usage,
)

# Ensure this example directory is on sys.path
_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))


# ── State ownership evaluator (not in shared telemetry) ────────────────


def evaluate_state_ownership(
    trace: Trace,
    allowed_keys: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Check that state transition events only write to allowed state keys.

    allowed_keys maps span kind -> list of permitted state keys.
    Returns a dict with metric name, passed bool, and details.
    """
    violations: list[str] = []
    for span in trace.spans:
        for event in span.events:
            if event.get("name") == "state_transition":
                state_key = (event.get("attributes") or {}).get("state_key", "")
                span_kind = span.kind
                if allowed_keys and span_kind in allowed_keys:
                    if state_key and state_key not in allowed_keys[span_kind]:
                        violations.append(
                            f"kind={span_kind}, key={state_key}"
                        )
    return {
        "metric": "state_ownership",
        "passed": len(violations) == 0,
        "details": f"violations={violations}" if violations else "none",
    }


def evaluate_citation_correctness(
    trace: Trace,
    expected_citations: list[str] | None = None,
) -> dict[str, Any]:
    """Check that tool_call spans have citation-related attributes."""
    tool_spans = [s for s in trace.spans if s.kind == "TOOL_CALL"]
    has_citations = all(
        "citation" in s.attributes or "source" in s.attributes
        for s in tool_spans
    )
    return {
        "metric": "citation_correctness",
        "passed": has_citations,
        "details": (
            f"{sum(1 for s in tool_spans if 'citation' in s.attributes or 'source' in s.attributes)}/"
            f"{len(tool_spans)} tool spans have citation info"
        ),
    }


def evaluate_argument_schema_alignment(
    trace: Trace,
) -> dict[str, Any]:
    """Check that tool_call spans have properly typed arguments."""
    tool_spans = [s for s in trace.spans if s.kind == "TOOL_CALL"]
    aligned = 0
    for s in tool_spans:
        args = s.attributes.get("arguments", {})
        if isinstance(args, dict) and "query" in args:
            aligned += 1
    return {
        "metric": "argument_schema_alignment",
        "passed": aligned == len(tool_spans),
        "details": f"{aligned}/{len(tool_spans)} tool spans have aligned args",
    }


# ── Fixture setup ──────────────────────────────────────────────────────


def build_model() -> ScriptedModel:
    """Create a ScriptedModel with all fixture responses."""
    model = ScriptedModel()

    # STEP 1: Classification responses
    model.register_fixture("classify_weather", text_response(
        "weather",
        prompt_tokens=15,
        completion_tokens=5,
    ))
    model.register_fixture("classify_time", text_response(
        "time",
        prompt_tokens=15,
        completion_tokens=5,
    ))
    model.register_fixture("classify_general", text_response(
        "general",
        prompt_tokens=15,
        completion_tokens=5,
    ))

    # STEP 2: Tool call responses (model asks to call lookup_tool)
    model.register_fixture("tool_weather", tool_call_response(
        tool_name="lookup_tool",
        arguments={"query": "weather in London", "type": "weather"},
        call_id="call_lookup_001",
    ))
    model.register_fixture("tool_time", tool_call_response(
        tool_name="lookup_tool",
        arguments={"query": "current time UTC", "type": "time"},
        call_id="call_lookup_002",
    ))
    model.register_fixture("tool_forbidden", tool_call_response(
        tool_name="exec_shell",
        arguments={"command": "rm -rf /"},
        call_id="call_forbidden_001",
    ))

    # STEP 3: Answer synthesis responses
    model.register_fixture("answer_weather", text_response(
        "The weather in London is 15°C with light rain.",
        prompt_tokens=20,
        completion_tokens=30,
    ))
    model.register_fixture("answer_time", text_response(
        "The current UTC time is 10:30 AM.",
        prompt_tokens=20,
        completion_tokens=25,
    ))
    model.register_fixture("answer_general", text_response(
        "I processed your general request successfully.",
        prompt_tokens=20,
        completion_tokens=20,
    ))

    return model


# ── Workflow step definitions ──────────────────────────────────────────


def _classify_request(
    model: ScriptedModel,
    request_text: str,
    trace: Trace,
    parent_span_id: str,
) -> str:
    """STEP 1: Model classifies the request type.

    Returns the classification label: 'weather', 'time', or 'general'.
    """
    span = trace.start_span(
        name="classify_request",
        kind="MODEL_CALL",
        parent_span_id=parent_span_id,
        attributes={"step": "classify"},
    )

    # Determine fixture key based on request text
    text_lower = request_text.lower()
    if "weather" in text_lower:
        fixture_key = "classify_weather"
    elif "time" in text_lower:
        fixture_key = "classify_time"
    else:
        fixture_key = "classify_general"

    # Simulate model call
    response = model.invoke(
        system_instruction="Classify the user request type.",
        messages=[{"role": "user", "content": f"__FIXTURE__:{fixture_key} {request_text}"}],
    )

    classification = response.text.strip()
    span.attributes["classification"] = classification
    span.attributes["prompt_tokens"] = response.usage.prompt_tokens
    span.attributes["completion_tokens"] = response.usage.completion_tokens
    span.attributes["total_tokens"] = response.usage.total_tokens
    span.add_event("state_transition", {
        "state_key": "classification",
        "value": classification,
    })
    span.finish("OK")
    return classification


def _route_decision(
    classification: str,
    trace: Trace,
    parent_span_id: str,
) -> str:
    """Determine the appropriate tool and action based on classification."""
    span = trace.start_span(
        name="route_decision",
        kind="ROUTING",
        parent_span_id=parent_span_id,
        attributes={"classification": classification},
    )

    tool_map = {
        "weather": "lookup_tool",
        "time": "lookup_tool",
        "general": "lookup_tool",
    }
    selected_tool = tool_map.get(classification, "lookup_tool")
    span.attributes["selected_tool"] = selected_tool
    span.add_event("state_transition", {
        "state_key": "selected_tool",
        "value": selected_tool,
    })
    span.finish("OK")
    return selected_tool


def _validate_classification(
    classification: str,
    trace: Trace,
    parent_span_id: str,
) -> bool:
    """Validate the classification result."""
    span = trace.start_span(
        name="validate_classification",
        kind="VALIDATION",
        parent_span_id=parent_span_id,
        attributes={"classification": classification},
    )

    valid = classification in ("weather", "time", "general")
    span.attributes["valid"] = str(valid)
    span.finish("OK" if valid else "ERROR")
    return valid


def _tool_lookup(
    model: ScriptedModel,
    classification: str,
    trace: Trace,
    parent_span_id: str,
    tool_latency_ms: float = 15.0,
) -> tuple[str, dict[str, Any]]:
    """STEP 2: Model calls a lookup tool with typed arguments."""
    # First, model call span for the tool-call request
    model_span = trace.start_span(
        name="tool_lookup_request",
        kind="MODEL_CALL",
        parent_span_id=parent_span_id,
        attributes={"step": "tool_lookup", "classification": classification},
    )

    fixture_key = f"tool_{classification}"
    response = model.invoke(
        system_instruction="Call the appropriate lookup tool with arguments.",
        messages=[
            {"role": "user", "content": f"__FIXTURE__:{fixture_key} Look up data."}
        ],
    )

    model_span.attributes["tool_call_requested"] = (
        response.tool_calls[0].name if response.tool_calls else ""
    )
    model_span.attributes["prompt_tokens"] = response.usage.prompt_tokens
    model_span.attributes["completion_tokens"] = response.usage.completion_tokens
    model_span.attributes["total_tokens"] = response.usage.total_tokens
    model_span.add_event("state_transition", {
        "state_key": "tool_request",
        "value": response.tool_calls[0].name if response.tool_calls else "",
    })
    model_span.finish("OK")

    # Then, tool call span
    tool_name = response.tool_calls[0].name if response.tool_calls else "lookup_tool"
    arguments = response.tool_calls[0].arguments if response.tool_calls else {}

    tool_span = trace.start_span(
        name=tool_name,
        kind="TOOL_CALL",
        parent_span_id=parent_span_id,
        attributes={
            "tool_name": tool_name,
            "arguments": arguments,
            "step": "tool_execution",
        },
    )

    # Simulate tool latency
    time.sleep(tool_latency_ms / 1000.0)

    # Generate result
    result = _simulate_lookup(classification, arguments)
    tool_span.attributes["result"] = result.get("value", "")
    tool_span.attributes["citation"] = result.get("citation", "")
    tool_span.attributes["source"] = result.get("source", "")
    tool_span.attributes["duration_ms"] = tool_latency_ms
    tool_span.add_event("state_transition", {
        "state_key": "tool_result",
        "value": result.get("value", ""),
    })
    tool_span.finish("OK")

    return tool_name, arguments


def _simulate_lookup(classification: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Simulate a tool lookup returning data."""
    query = arguments.get("query", "")
    if "weather" in query.lower() or classification == "weather":
        return {
            "value": "15°C, light rain",
            "citation": "weather-api-v2",
            "source": "openweather",
        }
    elif "time" in query.lower() or classification == "time":
        return {
            "value": "10:30 AM UTC",
            "citation": "time-api-v1",
            "source": "timezone-db",
        }
    else:
        return {
            "value": "general data returned",
            "citation": "general-db",
            "source": "knowledge-base",
        }


def _validate_arguments(
    tool_name: str,
    arguments: dict[str, Any],
    trace: Trace,
    parent_span_id: str,
) -> bool:
    """Validate tool arguments against expected schema."""
    span = trace.start_span(
        name="validate_arguments",
        kind="VALIDATION",
        parent_span_id=parent_span_id,
        attributes={
            "tool_name": tool_name,
            "arguments": arguments,
        },
    )

    # Validate that arguments have required keys
    has_query = "query" in arguments
    has_type = "type" in arguments
    valid = has_query and has_type
    span.attributes["schema_valid"] = str(valid)
    span.attributes["has_query"] = str(has_query)
    span.attributes["has_type"] = str(has_type)
    span.finish("OK" if valid else "ERROR")
    return valid


def _synthesize_answer(
    model: ScriptedModel,
    classification: str,
    tool_result: str,
    trace: Trace,
    parent_span_id: str,
) -> str:
    """STEP 3: Model synthesizes the final answer."""
    span = trace.start_span(
        name="synthesize_answer",
        kind="MODEL_CALL",
        parent_span_id=parent_span_id,
        attributes={
            "step": "answer",
            "classification": classification,
            "tool_result": tool_result,
        },
    )

    fixture_key = f"answer_{classification}"
    response = model.invoke(
        system_instruction="Synthesize the final answer from the lookup result.",
        messages=[
            {
                "role": "user",
                "content": (
                    f"__FIXTURE__:{fixture_key} "
                    f"Classification: {classification}, "
                    f"Tool result: {tool_result}"
                ),
            }
        ],
    )

    answer = response.text.strip()
    span.attributes["answer_length"] = len(answer)
    span.attributes["prompt_tokens"] = response.usage.prompt_tokens
    span.attributes["completion_tokens"] = response.usage.completion_tokens
    span.attributes["total_tokens"] = response.usage.total_tokens
    span.add_event("state_transition", {
        "state_key": "final_answer",
        "value": answer,
    })
    span.finish("OK")
    return answer


def _validate_answer(
    answer: str,
    trace: Trace,
    parent_span_id: str,
) -> bool:
    """Validate the final answer."""
    span = trace.start_span(
        name="validate_answer",
        kind="VALIDATION",
        parent_span_id=parent_span_id,
        attributes={"answer_length": len(answer)},
    )

    valid = len(answer) > 0
    span.attributes["valid"] = str(valid)
    span.finish("OK" if valid else "ERROR")
    return valid


def _record_tool_latency_report(
    tool_name: str,
    duration_ms: float,
    trace: Trace,
    parent_span_id: str,
) -> None:
    """Record a state_transition event for tool latency."""
    span = trace.start_span(
        name="tool_latency_report",
        kind="STATE_TRANSITION",
        parent_span_id=parent_span_id,
        attributes={
            "tool_name": tool_name,
            "duration_ms": duration_ms,
        },
    )
    span.add_event("state_transition", {
        "state_key": "tool_latency",
        "value": f"{tool_name}:{duration_ms}ms",
    })
    span.finish("OK")


# ── Main pipeline ──────────────────────────────────────────────────────


def run(
    scenario: str = "success",
    request_text: str | None = None,
) -> dict[str, Any]:
    """Execute the observability and evaluation workflow.

    Args:
        scenario: 'success', 'failure', 'forbidden_tool', or 'state_violation'.
        request_text: Optional custom request text.

    Returns:
        Dict with trace data and evaluation results.
    """
    # Build model and exporter
    model = build_model()
    exporter = InMemoryExporter()

    # Configure scenario
    scenario_texts = {
        "success": "What's the weather in London?",
        "failure": "",  # Empty request leads to empty response
        "forbidden_tool": "forbidden_tool_test",
        "state_violation": "What's the current time?",
    }
    request = request_text or scenario_texts.get(scenario, "What's the weather in London?")

    # Create trace
    trace = exporter.create_trace()

    # ── Step 1: Classify request type ──────────────────────────────────
    root_span = trace.start_span(
        name="observability_workflow",
        kind="INTERNAL",
        attributes={
            "scenario": scenario,
            "request": request,
            "budget.max_model_calls": 3,
            "budget.max_tool_calls": 2,
        },
    )

    classification = _classify_request(model, request, trace, root_span.span_id)

    # ── Validate classification ────────────────────────────────────────
    classification_valid = _validate_classification(classification, trace, root_span.span_id)

    if not classification_valid:
        root_span.add_event("state_transition", {
            "state_key": "workflow_status",
            "value": "classification_failed",
        })
        # Still routing but with a default
        selected_tool = "lookup_tool"
    else:
        # ── Route decision ──────────────────────────────────────────────
        selected_tool = _route_decision(classification, trace, root_span.span_id)

    # ── Check for forbidden tool scenario ──────────────────────────────
    forbidden_tool_used = False
    if scenario == "forbidden_tool":
        # Simulate a forbidden tool call
        forbidden_span = trace.start_span(
            name="exec_shell",
            kind="TOOL_CALL",
            parent_span_id=root_span.span_id,
            attributes={
                "tool_name": "exec_shell",
                "command": "rm -rf /",
                "arguments": {"command": "rm -rf /"},
            },
        )
        forbidden_span.finish("ERROR")
        forbidden_tool_used = True

    # ── State violation scenario: write to disallowed key ──────────────
    if scenario == "state_violation":
        violation_span = trace.start_span(
            name="disallowed_write",
            kind="INTERNAL",
            parent_span_id=root_span.span_id,
            attributes={"step": "violation"},
        )
        violation_span.add_event("state_transition", {
            "state_key": "disallowed_key__internal",
            "value": "tampered",
        })
        violation_span.finish("OK")

    # ── Step 2: Tool lookup (only if classification was valid) ─────────
    tool_name = ""
    arguments: dict[str, Any] = {}
    args_valid = False
    if classification_valid and scenario != "forbidden_tool":
        tool_name, arguments = _tool_lookup(
            model, classification, trace, root_span.span_id, tool_latency_ms=15.0,
        )

        # ── Validate arguments ──────────────────────────────────────────
        args_valid = _validate_arguments(tool_name, arguments, trace, root_span.span_id)

        # ── Record tool latency ────────────────────────────────────────
        _record_tool_latency_report(tool_name, 15.0, trace, root_span.span_id)

    # ── Step 3: Synthesize answer ─────────────────────────────────────
    tool_result_str = str(arguments.get("query", ""))
    answer = _synthesize_answer(
        model, classification or "general", tool_result_str, trace, root_span.span_id,
    )

    # ── Validate answer ───────────────────────────────────────────────
    answer_valid = _validate_answer(answer, trace, root_span.span_id)

    # ── Finalize root span ────────────────────────────────────────────
    root_span.add_event("state_transition", {
        "state_key": "workflow_status",
        "value": "completed",
    })
    root_span.finish("OK")

    # ── Evaluation ────────────────────────────────────────────────────
    evaluation_results: dict[str, Any] = {}

    # Task completion
    eval_completion = evaluate_task_completion(trace)
    evaluation_results[eval_completion["metric"]] = eval_completion

    # Maximum steps
    eval_steps = evaluate_maximum_steps(trace, max_steps=3)
    evaluation_results[eval_steps["metric"]] = eval_steps

    # Schema validity
    eval_schema = evaluate_schema_validity(trace)
    evaluation_results[eval_schema["metric"]] = eval_schema

    # Forbidden tool usage
    eval_forbidden = evaluate_forbidden_tool_usage(
        trace, forbidden=["exec_shell", "delete_tool"],
    )
    evaluation_results[eval_forbidden["metric"]] = eval_forbidden

    # State ownership
    allowed_keys = {
        "MODEL_CALL": ["classification", "tool_request", "final_answer"],
        "TOOL_CALL": ["tool_result"],
        "ROUTING": ["selected_tool"],
        "VALIDATION": [],
        "STATE_TRANSITION": ["tool_latency"],
        "INTERNAL": ["workflow_status"],
    }
    eval_ownership = evaluate_state_ownership(trace, allowed_keys=allowed_keys)
    evaluation_results[eval_ownership["metric"]] = eval_ownership

    # Argument schema alignment
    eval_schema_alignment = evaluate_argument_schema_alignment(trace)
    evaluation_results[eval_schema_alignment["metric"]] = eval_schema_alignment

    # Citation correctness
    eval_citation = evaluate_citation_correctness(trace)
    evaluation_results[eval_citation["metric"]] = eval_citation

    # ── Compute synthetic metrics ─────────────────────────────────────
    total_prompt_tokens = sum(
        s.attributes.get("prompt_tokens", 0)
        for s in trace.spans
        if s.kind == "MODEL_CALL"
    )
    total_completion_tokens = sum(
        s.attributes.get("completion_tokens", 0)
        for s in trace.spans
        if s.kind == "MODEL_CALL"
    )
    total_tokens = total_prompt_tokens + total_completion_tokens

    model_call_count = sum(1 for s in trace.spans if s.kind == "MODEL_CALL")
    tool_call_count = sum(1 for s in trace.spans if s.kind == "TOOL_CALL")
    completion_ok = eval_completion["passed"]

    cost_per_success = 0.0
    if completion_ok:
        cost_per_success = total_tokens / 100.0  # synthetic cost: 1¢ per 100 tokens

    groundedness_score = 1.0 if answer_valid else 0.0
    schema_validity_rate = (
        1.0 if eval_schema["passed"] else 0.0
    )
    failure_category = "none" if completion_ok else "task_failed"

    # ── Build output ──────────────────────────────────────────────────
    trace_output = trace.to_dict()

    output = {
        "scenario": scenario,
        "request": request,
        "classification": classification,
        "selected_tool": selected_tool if classification_valid else "",
        "tool_name": tool_name,
        "arguments": arguments,
        "args_valid": args_valid,
        "answer": answer,
        "answer_valid": answer_valid,
        "success": completion_ok,
        "forbidden_tool_used": forbidden_tool_used,
    }

    synthetic_metrics = {
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "total_tokens": total_tokens,
        "model_call_count": model_call_count,
        "tool_call_count": tool_call_count,
        "cost_per_success": cost_per_success,
        "groundedness_score": groundedness_score,
        "schema_validity_rate": schema_validity_rate,
        "failure_category": failure_category,
    }

    result = {
        "trace": trace_output,
        "output": output,
        "evaluation_results": evaluation_results,
        "synthetic_metrics": synthetic_metrics,
    }
    result["status"] = "succeeded" if completion_ok else "failed"

    return result
