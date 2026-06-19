"""Fixtures for Pattern 21: Budget-Aware Model Routing.

All fixture data is defined in agent.py because digit-prefixed directory
names aren't valid Python packages. This file re-exports for convenience.
"""

from __future__ import annotations

import sys
from pathlib import Path

_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))

from agent import (  # noqa: E402  # isort:skip
    CHEAP_FIXTURES,
    COMPLEX_REQUEST,
    EXPENSIVE_FIXTURES,
    MEDIUM_FIXTURES,
    MEDIUM_REQUEST,
    SIMPLE_REQUEST,
    VALID_RESPONSES,
)

__all__ = [
    "CHEAP_FIXTURES",
    "MEDIUM_FIXTURES",
    "EXPENSIVE_FIXTURES",
    "VALID_RESPONSES",
    "SIMPLE_REQUEST",
    "MEDIUM_REQUEST",
    "COMPLEX_REQUEST",
]
