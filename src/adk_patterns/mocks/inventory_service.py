"""Mock inventory/order service for offline testing."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class OrderStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class InventoryError(Exception):
    """Inventory operation failed."""


@dataclass
class OrderItem:
    item_id: str
    name: str
    quantity: int
    price: float


@dataclass
class Order:
    order_id: str
    customer_id: str
    items: list[OrderItem] = field(default_factory=list)
    status: OrderStatus = OrderStatus.PENDING
    metadata: dict[str, Any] = field(default_factory=dict)


class MockInventoryService:
    """Mock inventory service with order management, reservations, and concurrency."""

    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}
        self._inventory: dict[str, int] = {}
        self._reservations: dict[str, int] = {}
        self._fail_next: bool = False

    def add_inventory(self, item_id: str, quantity: int) -> None:
        self._inventory[item_id] = self._inventory.get(item_id, 0) + quantity

    def create_order(self, order_id: str, customer_id: str, items: list[OrderItem]) -> Order:
        order = Order(order_id=order_id, customer_id=customer_id, items=items)
        self._orders[order_id] = order
        return order

    def get_order(self, order_id: str) -> Order | None:
        if self._fail_next:
            self._fail_next = False
            raise InventoryError("Simulated service failure")
        return self._orders.get(order_id)

    def reserve_item(self, item_id: str, quantity: int) -> bool:
        available = self._inventory.get(item_id, 0) - self._reservations.get(item_id, 0)
        if available < quantity:
            return False
        self._reservations[item_id] = self._reservations.get(item_id, 0) + quantity
        return True

    def release_reservation(self, item_id: str, quantity: int) -> None:
        current = self._reservations.get(item_id, 0)
        self._reservations[item_id] = max(0, current - quantity)

    def set_concurrency_conflict(self) -> None:
        """Simulate a stale state / concurrency conflict."""
        self._fail_next = True

    def reset(self) -> None:
        self._orders.clear()
        self._inventory.clear()
        self._reservations.clear()
        self._fail_next = False
