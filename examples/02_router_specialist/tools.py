"""Tool definitions and permission enforcement for Pattern 02: Router-Specialist.

Standalone reference copy — see agent.py for the authoritative definitions.
"""

from __future__ import annotations

from .mocks import SPECIALIST_TOOL_MAP


def get_tools_for_specialist(specialist: str) -> dict[str, object]:
    """Return the tool set available to a given specialist."""
    return SPECIALIST_TOOL_MAP.get(specialist, {})


def check_tool_permission(specialist: str, tool_name: str) -> bool:
    """Verify a specialist is allowed to use a specific tool."""
    allowed_tools = SPECIALIST_TOOL_MAP.get(specialist, {})
    return tool_name in allowed_tools
