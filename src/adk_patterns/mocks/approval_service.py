"""Mock approval service for human-in-the-loop patterns."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ApprovalVerdict(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AMENDED = "amended"
    TIMED_OUT = "timed_out"


@dataclass
class ApprovalRequest:
    request_id: str
    action: str
    resource: str
    proposed_by: str
    details: dict[str, Any] = field(default_factory=dict)
    verdict: ApprovalVerdict = ApprovalVerdict.PENDING
    reviewer: str | None = None
    reviewer_note: str | None = None


class MockApprovalService:
    """Mock approval service with deterministic test responses.

    Does NOT implement production cryptography. Clearly labeled as educational mock.
    """

    def __init__(self) -> None:
        self._requests: dict[str, ApprovalRequest] = {}
        self._auto_approve: bool = False
        self._auto_reject: bool = False
        self._timeout: bool = False

    def submit(self, request: ApprovalRequest) -> ApprovalRequest:
        self._requests[request.request_id] = request
        if self._timeout:
            request.verdict = ApprovalVerdict.TIMED_OUT
        elif self._auto_approve:
            request.verdict = ApprovalVerdict.APPROVED
            request.reviewer = "auto-approver"
        elif self._auto_reject:
            request.verdict = ApprovalVerdict.REJECTED
            request.reviewer = "auto-rejecter"
        return request

    def approve(self, request_id: str, reviewer: str, note: str = "") -> ApprovalRequest:
        req = self._requests.get(request_id)
        if not req:
            raise ValueError(f"Approval request {request_id} not found")
        req.verdict = ApprovalVerdict.APPROVED
        req.reviewer = reviewer
        req.reviewer_note = note
        return req

    def reject(self, request_id: str, reviewer: str, note: str = "") -> ApprovalRequest:
        req = self._requests.get(request_id)
        if not req:
            raise ValueError(f"Approval request {request_id} not found")
        req.verdict = ApprovalVerdict.REJECTED
        req.reviewer = reviewer
        req.reviewer_note = note
        return req

    def get(self, request_id: str) -> ApprovalRequest | None:
        return self._requests.get(request_id)

    def set_auto_approve(self) -> None:
        self._auto_approve = True

    def set_auto_reject(self) -> None:
        self._auto_reject = True

    def set_timeout(self) -> None:
        self._timeout = True

    def reset(self) -> None:
        self._requests.clear()
        self._auto_approve = False
        self._auto_reject = False
        self._timeout = False
