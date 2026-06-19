"""Contracts for Pattern 21: Budget-Aware Model Routing.

All contract definitions are inlined in agent.py because digit-prefixed
directory names aren't valid Python packages, preventing relative imports.
This file re-exports for convenience and backwards compatibility.
"""

from __future__ import annotations

import sys
from pathlib import Path

_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))

from agent import (  # noqa: E402  # isort:skip
    ComplexityClass,
    ESCALATION_ORDER,
    MAX_ESCALATIONS,
    ModelTier,
    RoutingDecision,
    TIER_METADATA,
)

__all__ = [
    "ComplexityClass",
    "ModelTier",
    "RoutingDecision",
    "TIER_METADATA",
    "ESCALATION_ORDER",
    "MAX_ESCALATIONS",
]
