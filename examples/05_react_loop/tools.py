"""Tool implementations for Pattern 05: ReAct Loop.

Read-only tools for querying metrics, logs, and deployment history.
submit_diagnosis is a termination tool that records the final diagnosis."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from adk_patterns.shared import RunContext

# Add this directory to path so we can import sibling modules
_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))

from contracts import (  # noqa: E402
    GetDeploymentHistoryRequest,
    GetDeploymentHistoryResult,
    QueryLogsRequest,
    QueryLogsResult,
    QueryMetricsRequest,
    QueryMetricsResult,
    SubmitDiagnosisRequest,
)
from mocks import get_shared_data  # noqa: E402


def query_metrics(service: str, metric: str) -> dict[str, Any]:
    """Query a service's metric value.

    Args:
        service: Service name (e.g., api-gateway, user-service).
        metric: Metric name (e.g., cpu_usage, error_rate, latency_p99).

    Returns:
        A dict with service, metric, value, unit, timestamp, and healthy flag.
    """
    data = get_shared_data()
    service_metrics = data.metrics.get(service)

    if service_metrics is None:
        return QueryMetricsResult(
            service=service,
            metric=metric,
            value=0.0,
            unit="",
            timestamp="",
            healthy=False,
        ).model_dump()

    value = service_metrics.get(metric, 0.0)

    # Determine unit based on metric name
    unit_map = {
        "cpu_usage": "%",
        "memory_usage": "%",
        "error_rate": "%",
        "latency_p99": "ms",
        "request_rate": "req/s",
    }
    unit = unit_map.get(metric, "")

    # Determine health status
    thresholds = {
        "cpu_usage": 80.0,
        "memory_usage": 80.0,
        "error_rate": 5.0,
        "latency_p99": 500.0,
    }
    threshold = thresholds.get(metric, float("inf"))
    healthy = value < threshold if threshold != float("inf") else True

    return QueryMetricsResult(
        service=service,
        metric=metric,
        value=value,
        unit=unit,
        timestamp="2026-06-19T10:30:00Z",
        healthy=healthy,
    ).model_dump()


def query_logs(service: str, timeframe: str = "last_15m") -> dict[str, Any]:
    """Query recent log entries for a service.

    Args:
        service: Service name (e.g., api-gateway, user-service).
        timeframe: Time range (e.g., last_15m, last_1h, last_24h).

    Returns:
        A dict with service, entries, error_count, and timeframe.
    """
    data = get_shared_data()
    entries = data.logs.get(service, [])
    error_count = sum(e.get("count", 0) for e in entries if e.get("level") == "ERROR")

    return QueryLogsResult(
        service=service,
        entries=entries,
        error_count=error_count,
        timeframe=timeframe,
    ).model_dump()


def get_deployment_history(service: str) -> dict[str, Any]:
    """Get recent deployment history for a service.

    Args:
        service: Service name (e.g., api-gateway, user-service).

    Returns:
        A dict with service, deployments, and recent_changes.
    """
    data = get_shared_data()
    deployments = data.deployments.get(service, [])

    # Extract recent change descriptions
    recent_changes = []
    for dep in deployments:
        recent_changes.extend(dep.get("changes", []))

    return GetDeploymentHistoryResult(
        service=service,
        deployments=deployments,
        recent_changes=recent_changes,
    ).model_dump()


def submit_diagnosis(diagnosis: str, root_cause: str) -> dict[str, Any]:
    """Submit a final diagnosis for the incident (termination tool).

    This tool ends the reasoning loop. After calling this, the agent
    should provide its final answer.

    Args:
        diagnosis: Summary of the diagnosis.
        root_cause: Identified root cause of the incident.

    Returns:
        A dict confirming the diagnosis was recorded.
    """
    data = get_shared_data()
    result = data.submit_diagnosis()

    return {
        "status": result["status"],
        "submission_id": result["submission_id"],
        "diagnosis": diagnosis,
        "root_cause": root_cause,
    }


def tool_definitions() -> list[dict[str, Any]]:
    """Return tool definitions in an ADK-compatible format."""
    return [
        {
            "name": "query_metrics",
            "description": "Query a service's metric value (e.g., cpu_usage, error_rate, latency_p99). Returns value, unit, and health status.",
            "parameters": {
                "service": {"type": "string", "description": "Service name (e.g., api-gateway, user-service, payment-service)"},
                "metric": {"type": "string", "description": "Metric name (e.g., cpu_usage, memory_usage, error_rate, latency_p99, request_rate)"},
            },
        },
        {
            "name": "query_logs",
            "description": "Query recent log entries for a service. Returns log entries with error count.",
            "parameters": {
                "service": {"type": "string", "description": "Service name (e.g., api-gateway, user-service, payment-service)"},
                "timeframe": {"type": "string", "description": "Time range (e.g., last_15m, last_1h, last_24h)"},
            },
        },
        {
            "name": "get_deployment_history",
            "description": "Get recent deployment history for a service. Returns version history and recent changes.",
            "parameters": {
                "service": {"type": "string", "description": "Service name (e.g., api-gateway, user-service, payment-service)"},
            },
        },
        {
            "name": "submit_diagnosis",
            "description": "TERMINAL TOOL: Submit a final diagnosis for the incident. Call this when you have enough evidence to conclude. After this, provide your final answer.",
            "parameters": {
                "diagnosis": {"type": "string", "description": "Summary of the diagnosis"},
                "root_cause": {"type": "string", "description": "Identified root cause of the incident"},
            },
        },
    ]


TOOL_REGISTRY: dict[str, Any] = {
    "query_metrics": query_metrics,
    "query_logs": query_logs,
    "get_deployment_history": get_deployment_history,
    "submit_diagnosis": submit_diagnosis,
}


def validate_and_execute(tool_name: str, arguments: dict[str, Any]) -> Any:
    """Execute a tool with runtime type validation.

    Raises:
        ValueError: If the tool is unknown.
        TypeError: If any argument has the wrong type.
    """
    if tool_name not in TOOL_REGISTRY:
        msg = f"Tool '{tool_name}' is not available. Available tools: {', '.join(sorted(TOOL_REGISTRY))}"
        raise ValueError(msg)

    fn = TOOL_REGISTRY[tool_name]

    # Type validation: ensure string parameters are actually strings
    import inspect
    import typing

    sig = inspect.signature(fn)
    try:
        hints = typing.get_type_hints(fn)
    except Exception:
        hints = {}

    for param_name, param in sig.parameters.items():
        if param_name in arguments:
            actual_value = arguments[param_name]
            expected_type = hints.get(param_name, param.annotation)
            if expected_type is str and not isinstance(actual_value, str):
                raise TypeError(
                    f"Argument '{param_name}' must be str, "
                    f"got {type(actual_value).__name__} ({actual_value!r})"
                )

    return fn(**arguments)
