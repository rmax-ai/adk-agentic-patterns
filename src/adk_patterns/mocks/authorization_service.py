"""Mock authorization service. Educational mock — NOT production-grade cryptography."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AuthzVerdict(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass
class AuthzRequest:
    principal: str
    action: str
    resource: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuthzResponse:
    verdict: AuthzVerdict
    reason: str = ""
    matched_rule: str = ""


class MockAuthorizationService:
    """Mock authorization service with rule-based allow/deny.

    EDUCATIONAL MOCK — does not implement production cryptography or
    capability-based security. Models attenuated authorization conceptually.
    """

    def __init__(self) -> None:
        self._rules: list[dict[str, Any]] = []
        self._default_verdict: AuthzVerdict = AuthzVerdict.DENY

    def add_rule(
        self,
        principal: str,
        action: str,
        resource: str,
        verdict: AuthzVerdict = AuthzVerdict.ALLOW,
    ) -> None:
        self._rules.append(
            {
                "principal": principal,
                "action": action,
                "resource": resource,
                "verdict": verdict,
            }
        )

    def allow_all(self) -> None:
        self._default_verdict = AuthzVerdict.ALLOW

    def check(self, request: AuthzRequest) -> AuthzResponse:
        for rule in self._rules:
            if (
                (rule["principal"] == "*" or rule["principal"] == request.principal)
                and (rule["action"] == "*" or rule["action"] == request.action)
                and (rule["resource"] == "*" or rule["resource"] == request.resource)
            ):
                return AuthzResponse(verdict=rule["verdict"], reason="rule_match")
        return AuthzResponse(verdict=self._default_verdict, reason="default")

    def reset(self) -> None:
        self._rules.clear()
        self._default_verdict = AuthzVerdict.DENY
