"""Typed contracts for Pattern 04: Tool-Using Agent.

Every tool input and output has a Pydantic schema so the model's typed
arguments are validated at runtime.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class OrderStatusRequest(BaseModel):
    """Request to look up an order's current status."""

    order_id: str = Field(description="Order identifier (e.g., ORD-001)")


class OrderItem(BaseModel):
    """A single line item on an order."""

    item_id: str
    name: str
    quantity: int
    price: float


class OrderStatusResult(BaseModel):
    """Full order status including items and customer reference."""

    order_id: str
    status: str
    customer_id: str
    items: list[OrderItem] = Field(default_factory=list)


class ShipmentStatusRequest(BaseModel):
    """Request to look up a shipment by tracking number."""

    tracking_id: str = Field(description="Tracking identifier (e.g., TRK-999)")


class ShipmentStatusResult(BaseModel):
    """Current shipment tracking information."""

    tracking_id: str
    status: str
    estimated_delivery: str | None = None


class CustomerInfoRequest(BaseModel):
    """Request for customer profile information."""

    customer_id: str = Field(description="Customer identifier (e.g., CUST-042)")


class CustomerInfoResult(BaseModel):
    """Customer profile data."""

    customer_id: str
    name: str
    email: str
