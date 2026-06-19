"""Mock services for Pattern 06: Planner-Executor.

Simulates venue, catering, and calendar services for conference setup.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MockVenueService:
    """Mock venue service with book, cancel, and availability check."""

    venues: dict[str, dict] = field(default_factory=lambda: {
        "venue-001": {"id": "venue-001", "name": "Grand Ballroom", "capacity": 300, "available": True},
        "venue-002": {"id": "venue-002", "name": "Conference Hall A", "capacity": 150, "available": True},
        "venue-003": {"id": "venue-003", "name": "Meeting Room B", "capacity": 50, "available": False},
    })
    bookings: dict[str, dict] = field(default_factory=dict)

    def check_availability(self, venue_id: str) -> dict:
        """Check if a venue is available."""
        venue = self.venues.get(venue_id)
        if venue is None:
            return {"venue_id": venue_id, "available": False, "error": "venue not found"}
        return {
            "venue_id": venue_id,
            "name": venue["name"],
            "capacity": venue["capacity"],
            "available": venue["available"],
        }

    def book_venue(self, venue_id: str) -> dict:
        """Book a venue. Success unless venue unavailable or already booked."""
        venue = self.venues.get(venue_id)
        if venue is None:
            return {"venue_id": venue_id, "success": False, "error": "venue not found"}
        if not venue["available"]:
            return {"venue_id": venue_id, "success": False, "error": "venue not available"}
        if venue_id in self.bookings:
            return {"venue_id": venue_id, "success": False, "error": "venue already booked"}
        self.bookings[venue_id] = {"status": "booked", "venue_name": venue["name"]}
        return {"venue_id": venue_id, "success": True, "status": "booked", "venue_name": venue["name"]}

    def cancel_venue(self, venue_id: str) -> dict:
        """Cancel a venue booking."""
        if venue_id not in self.bookings:
            return {"venue_id": venue_id, "success": False, "error": "no booking to cancel"}
        del self.bookings[venue_id]
        return {"venue_id": venue_id, "success": True, "status": "cancelled"}


@dataclass
class MockCateringService:
    """Mock catering service for ordering conference catering."""

    orders: dict[str, dict] = field(default_factory=dict)

    def order_catering(self, venue_id: str, attendees: int) -> dict:
        """Place a catering order for a venue."""
        order_id = f"cater-{len(self.orders) + 1:03d}"
        self.orders[order_id] = {
            "venue_id": venue_id,
            "attendees": attendees,
            "status": "confirmed",
            "menu": "standard conference menu",
        }
        return {
            "order_id": order_id,
            "venue_id": venue_id,
            "attendees": attendees,
            "status": "confirmed",
        }


@dataclass
class MockCalendarService:
    """Mock calendar service for scheduling conference events."""

    events: dict[str, dict] = field(default_factory=dict)

    def schedule_event(self, title: str, date: str, venue_id: str) -> dict:
        """Schedule an event on the calendar."""
        event_id = f"evt-{len(self.events) + 1:03d}"
        self.events[event_id] = {
            "title": title,
            "date": date,
            "venue_id": venue_id,
            "status": "scheduled",
        }
        return {
            "event_id": event_id,
            "title": title,
            "date": date,
            "venue_id": venue_id,
            "status": "scheduled",
        }
