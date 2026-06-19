"""Typed contracts for Pattern 05: ReAct Loop.

Every tool input and output has a Pydantic schema so the model's typed
arguments are validated at runtime.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DiagnosisResult(BaseModel):
    """Typed diagnosis output produced when the agent submits a final diagnosis."""

    category: str = Field(description="Incident category (e.g., infrastructure, application, network)")
    root_cause: str = Field(description="Identified root cause of the incident")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in the diagnosis (0.0–1.0)")
    evidence: list[str] = Field(default_factory=list, description="Evidence items supporting the diagnosis")


class QueryMetricsRequest(BaseModel):
    """Request to query a service metric."""

    service: str = Field(description="Service name to query (e.g., api-gateway, user-service)")
    metric: str = Field(description="Metric name (e.g., cpu_usage, error_rate, latency_p99)")


class QueryMetricsResult(BaseModel):
    """Result of a metrics query."""

    service: str
    metric: str
    value: float
    unit: str
    timestamp: str
    healthy: bool


class QueryLogsRequest(BaseModel):
    """Request to query service logs."""

    service: str = Field(description="Service name to query (e.g., api-gateway, user-service)")
    timeframe: str = Field(description="Time range (e.g., last_15m, last_1h, last_24h)")


class QueryLogsResult(BaseModel):
    """Result of a logs query."""

    service: str
    entries: list[dict] = Field(default_factory=list)
    error_count: int = 0
    timeframe: str


class GetDeploymentHistoryRequest(BaseModel):
    """Request to get deployment history for a service."""

    service: str = Field(description="Service name (e.g., api-gateway, user-service)")


class GetDeploymentHistoryResult(BaseModel):
    """Result of a deployment history query."""

    service: str
    deployments: list[dict] = Field(default_factory=list)
    recent_changes: list[str] = Field(default_factory=list)


class SubmitDiagnosisRequest(BaseModel):
    """Request to submit a final diagnosis (termination tool)."""

    diagnosis: str = Field(description="Summary of the diagnosis")
    root_cause: str = Field(description="Identified root cause")
