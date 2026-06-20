"""Lightweight in-memory OpenTelemetry-like trace exporter.

Captures trace IDs, span hierarchies, model-call spans, tool-call spans,
state-transition events, and synthetic metrics for offline evaluation.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Span:
    """A single span in a trace."""

    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    parent_span_id: str | None = None
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    name: str = ""
    kind: str = "INTERNAL"  # MODEL_CALL, TOOL_CALL, ROUTING, VALIDATION, STATE_TRANSITION
    start_time: float = field(default_factory=time.monotonic)
    end_time: float | None = None
    status: str = "UNSET"
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    def finish(self, status: str = "OK") -> None:
        self.end_time = time.monotonic()
        self.status = status

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        self.events.append(
            {
                "name": name,
                "timestamp": time.monotonic(),
                "attributes": attributes or {},
            }
        )

    @property
    def duration_ms(self) -> float:
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time) * 1000


@dataclass
class Trace:
    """A full trace containing spans."""

    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    spans: list[Span] = field(default_factory=list)
    root_span_id: str | None = None

    def start_span(
        self,
        name: str,
        kind: str = "INTERNAL",
        parent_span_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Span:
        """Start a new span within this trace."""
        span = Span(
            trace_id=self.trace_id,
            parent_span_id=parent_span_id or self.root_span_id,
            name=name,
            kind=kind,
            attributes=attributes or {},
        )
        self.spans.append(span)
        if self.root_span_id is None:
            self.root_span_id = span.span_id
        return span

    def to_dict(self) -> dict[str, Any]:
        """Export the trace as a dictionary."""
        return {
            "trace_id": self.trace_id,
            "spans": [
                {
                    "span_id": s.span_id,
                    "parent_span_id": s.parent_span_id,
                    "name": s.name,
                    "kind": s.kind,
                    "duration_ms": s.duration_ms,
                    "status": s.status,
                    "attributes": s.attributes,
                    "events": s.events,
                }
                for s in self.spans
            ],
        }


class InMemoryExporter:
    """Collects traces in memory for offline evaluation."""

    def __init__(self) -> None:
        self.traces: list[Trace] = []

    def create_trace(self) -> Trace:
        trace = Trace()
        self.traces.append(trace)
        return trace

    def get_traces(self) -> list[dict[str, Any]]:
        return [t.to_dict() for t in self.traces]

    def clear(self) -> None:
        self.traces.clear()


# -- Deterministic evaluators -----------------------------------------------


def evaluate_task_completion(trace: Trace, expected_status: str = "OK") -> dict[str, Any]:
    """Evaluate whether the trace shows successful task completion."""
    root_spans = [s for s in trace.spans if s.parent_span_id is None]
    completed = all(s.status == expected_status for s in root_spans)
    return {
        "metric": "task_completion",
        "passed": completed,
        "details": f"{sum(1 for s in root_spans if s.status == expected_status)}/{len(root_spans)} root spans OK",
    }


def evaluate_maximum_steps(trace: Trace, max_steps: int) -> dict[str, Any]:
    """Evaluate whether the trace respects step budgets."""
    tool_calls = sum(1 for s in trace.spans if s.kind == "TOOL_CALL")
    model_calls = sum(1 for s in trace.spans if s.kind == "MODEL_CALL")
    within_budget = tool_calls <= max_steps and model_calls <= max_steps
    return {
        "metric": "maximum_steps",
        "passed": within_budget,
        "details": f"tool_calls={tool_calls}, model_calls={model_calls}, max={max_steps}",
    }


def evaluate_schema_validity(trace: Trace, expected_valid: bool = True) -> dict[str, Any]:
    """Evaluate whether schema validation spans passed."""
    validation_spans = [s for s in trace.spans if s.kind == "VALIDATION"]
    if not validation_spans:
        return {"metric": "schema_validity", "passed": True, "details": "no validation spans"}
    all_ok = all(s.status == "OK" for s in validation_spans)
    return {
        "metric": "schema_validity",
        "passed": all_ok == expected_valid,
        "details": f"{sum(1 for s in validation_spans if s.status == 'OK')}/{len(validation_spans)} validations OK",
    }


def evaluate_forbidden_tool_usage(trace: Trace, forbidden: list[str]) -> dict[str, Any]:
    """Check that no forbidden tools were called."""
    tool_names = [s.attributes.get("tool_name", "") for s in trace.spans if s.kind == "TOOL_CALL"]
    violations = [t for t in tool_names if t in forbidden]
    return {
        "metric": "forbidden_tool_usage",
        "passed": len(violations) == 0,
        "details": f"violations={violations}" if violations else "none",
    }
