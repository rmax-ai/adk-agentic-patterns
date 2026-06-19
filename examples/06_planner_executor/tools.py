"""Scoped tool implementations for Pattern 06: Planner-Executor.

These tools are made available to the Executor but NOT to the Planner.
The Planner has no write tools — only read/plan capabilities.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Ensure this example directory is on sys.path for absolute imports
_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))

from mocks import MockCalendarService, MockCateringService, MockVenueService  # noqa: E402


# ---------------------------------------------------------------------------
# Tool definitions (scoped for the executor)
# ---------------------------------------------------------------------------


def tool_check_availability(venue_service: MockVenueService, venue_id: str) -> dict[str, Any]:
    """Check venue availability.

    Args:
        venue_id: Venue identifier (e.g., venue-001).

    Returns:
        Dict with venue_id, name, capacity, and available flag.
    """
    return venue_service.check_availability(venue_id)


def tool_book_venue(venue_service: MockVenueService, venue_id: str) -> dict[str, Any]:
    """Book a venue for the conference.

    Args:
        venue_id: Venue identifier (e.g., venue-001).

    Returns:
        Dict with venue_id, success flag, and status.
    """
    return venue_service.book_venue(venue_id)


def tool_cancel_venue(venue_service: MockVenueService, venue_id: str) -> dict[str, Any]:
    """Cancel a venue booking.

    Args:
        venue_id: Venue identifier (e.g., venue-001).

    Returns:
        Dict with venue_id, success flag, and status.
    """
    return venue_service.cancel_venue(venue_id)


def tool_order_catering(
    catering_service: MockCateringService, venue_id: str, attendees: int
) -> dict[str, Any]:
    """Order catering for the conference.

    Args:
        venue_id: Venue identifier for the catering venue.
        attendees: Number of attendees to cater for.

    Returns:
        Dict with order_id, venue_id, attendees, and status.
    """
    return catering_service.order_catering(venue_id, attendees)


def tool_schedule_event(
    calendar_service: MockCalendarService, title: str, date: str, venue_id: str
) -> dict[str, Any]:
    """Schedule an event on the calendar.

    Args:
        title: Event title (e.g., 'Annual Tech Conference').
        date: Event date in YYYY-MM-DD format.
        venue_id: Venue identifier.

    Returns:
        Dict with event_id, title, date, venue_id, and status.
    """
    return calendar_service.schedule_event(title, date, venue_id)


# ---------------------------------------------------------------------------
# Resolver — maps tool names to callable functions
# ---------------------------------------------------------------------------

ExecutorToolRegistry = dict[str, Any]

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "check_availability",
        "description": "Check if a venue is available. Returns availability, capacity, and venue name.",
        "parameters": {"venue_id": {"type": "string", "description": "Venue ID (e.g., venue-001)"}},
    },
    {
        "name": "book_venue",
        "description": "Book a venue for the conference. Returns success/failure and booking status.",
        "parameters": {"venue_id": {"type": "string", "description": "Venue ID (e.g., venue-001)"}},
    },
    {
        "name": "cancel_venue",
        "description": "Cancel a venue booking. Returns success/failure.",
        "parameters": {"venue_id": {"type": "string", "description": "Venue ID (e.g., venue-001)"}},
    },
    {
        "name": "order_catering",
        "description": "Order catering for a venue. Provide venue ID and number of attendees.",
        "parameters": {
            "venue_id": {"type": "string", "description": "Venue ID for catering"},
            "attendees": {"type": "integer", "description": "Number of attendees"},
        },
    },
    {
        "name": "schedule_event",
        "description": "Schedule a calendar event. Provide title, date, and venue ID.",
        "parameters": {
            "title": {"type": "string", "description": "Event title"},
            "date": {"type": "string", "description": "Event date in YYYY-MM-DD"},
            "venue_id": {"type": "string", "description": "Venue ID"},
        },
    },
]


def create_executor_tools(
    venue_service: MockVenueService,
    catering_service: MockCateringService,
    calendar_service: MockCalendarService,
) -> dict[str, Any]:
    """Create the executor tool registry with bound services."""
    return {
        "check_availability": lambda venue_id: tool_check_availability(venue_service, venue_id),
        "book_venue": lambda venue_id: tool_book_venue(venue_service, venue_id),
        "cancel_venue": lambda venue_id: tool_cancel_venue(venue_service, venue_id),
        "order_catering": lambda venue_id, attendees: tool_order_catering(
            catering_service, venue_id, attendees
        ),
        "schedule_event": lambda title, date, venue_id: tool_schedule_event(
            calendar_service, title, date, venue_id
        ),
    }
