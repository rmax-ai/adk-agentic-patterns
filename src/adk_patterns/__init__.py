"""ADK Agentic Design Patterns — Executable catalogue of agentic design patterns.

A tested, documented, locally-runnable reference implementation demonstrating
major design patterns for building reliable agentic systems with Google ADK.
"""

from adk_patterns.contracts import (
    AuditEvent,
    ExecutionStatus,
    PatternMetadata,
    PatternRunResult,
    RunBudget,
    ToolInvocationRecord,
)
from adk_patterns.registry import PATTERNS, get, list_all, register

__version__ = "0.1.0"
__all__ = [
    "PATTERNS",
    "AuditEvent",
    "ExecutionStatus",
    "PatternMetadata",
    "PatternRunResult",
    "RunBudget",
    "ToolInvocationRecord",
    "get",
    "list_all",
    "register",
]
