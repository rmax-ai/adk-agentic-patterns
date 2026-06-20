"""Mock payment service — supports authorize, capture, refund, reverse, idempotency."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class PaymentStatus(StrEnum):
    PENDING = "pending"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    REFUNDED = "refunded"
    REVERSED = "reversed"
    FAILED = "failed"


class PaymentError(Exception):
    """Payment operation failed."""


class DuplicateRequestError(PaymentError):
    """Duplicate idempotency key detected."""


@dataclass
class Payment:
    payment_id: str
    amount: float
    currency: str = "USD"
    status: PaymentStatus = PaymentStatus.PENDING
    idempotency_key: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class MockPaymentService:
    """Mock payment service for offline testing.

    Supports:
    - authorize, capture, refund, reverse
    - idempotency keys
    - partial failure injection
    - duplicate request detection
    """

    def __init__(self) -> None:
        self._payments: dict[str, Payment] = {}
        self._idempotency_keys: set[str] = set()
        self._fail_next: str | None = None

    def inject_failure(self, operation: str) -> None:
        """Make the next call to `operation` fail."""
        self._fail_next = operation

    def authorize(
        self, payment_id: str, amount: float, idempotency_key: str | None = None
    ) -> Payment:
        self._check_idempotency(idempotency_key)
        self._check_failure("authorize")
        payment = Payment(payment_id=payment_id, amount=amount, status=PaymentStatus.AUTHORIZED)
        self._payments[payment_id] = payment
        if idempotency_key:
            self._idempotency_keys.add(idempotency_key)
        return payment

    def capture(self, payment_id: str) -> Payment:
        self._check_failure("capture")
        payment = self._payments.get(payment_id)
        if not payment:
            raise PaymentError(f"Payment {payment_id} not found")
        if payment.status != PaymentStatus.AUTHORIZED:
            raise PaymentError(f"Cannot capture payment in status {payment.status}")
        payment.status = PaymentStatus.CAPTURED
        return payment

    def refund(self, payment_id: str, _amount: float | None = None) -> Payment:
        self._check_failure("refund")
        payment = self._payments.get(payment_id)
        if not payment:
            raise PaymentError(f"Payment {payment_id} not found")
        if payment.status != PaymentStatus.CAPTURED:
            raise PaymentError(f"Cannot refund payment in status {payment.status}")
        payment.status = PaymentStatus.REFUNDED
        return payment

    def reverse(self, payment_id: str) -> Payment:
        """Reverse an authorization (compensating action)."""
        self._check_failure("reverse")
        payment = self._payments.get(payment_id)
        if not payment:
            raise PaymentError(f"Payment {payment_id} not found")
        if payment.status not in (PaymentStatus.AUTHORIZED, PaymentStatus.CAPTURED):
            raise PaymentError(f"Cannot reverse payment in status {payment.status}")
        payment.status = PaymentStatus.REVERSED
        return payment

    def get_payment(self, payment_id: str) -> Payment | None:
        return self._payments.get(payment_id)

    def _check_failure(self, operation: str) -> None:
        if self._fail_next == operation:
            self._fail_next = None
            raise PaymentError(f"Injected failure for {operation}")

    def _check_idempotency(self, key: str | None) -> None:
        if key and key in self._idempotency_keys:
            raise DuplicateRequestError(f"Duplicate idempotency key: {key}")

    def reset(self) -> None:
        self._payments.clear()
        self._idempotency_keys.clear()
        self._fail_next = None
