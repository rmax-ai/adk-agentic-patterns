"""Mock code sandbox — predefined execution fixtures. Does NOT execute arbitrary code."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SandboxResult:
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class MockCodeSandbox:
    """Mock code sandbox with predefined execution fixtures.

    Does NOT execute arbitrary untrusted code on the host.
    All execution results are predefined fixtures for testing.
    """

    def __init__(self) -> None:
        self._fixtures: dict[str, SandboxResult] = {}
        self._forbidden_ops: list[str] = []
        self._timeout: bool = False

    def register(self, key: str, result: SandboxResult) -> None:
        self._fixtures[key] = result

    def execute(self, code: str, _language: str = "python") -> SandboxResult:
        """Return a predefined fixture result. Does not actually execute code."""
        if self._timeout:
            self._timeout = False
            return SandboxResult(success=False, stderr="Timeout", exit_code=124)

        # Check for forbidden operations
        for forbidden in self._forbidden_ops:
            if forbidden in code:
                return SandboxResult(
                    success=False,
                    stderr=f"Forbidden operation detected: {forbidden}",
                    exit_code=1,
                )

        # Try exact match first
        if code.strip() in self._fixtures:
            return self._fixtures[code.strip()]

        # Try key-based lookup
        for key, result in self._fixtures.items():
            if key in code:
                return result

        return SandboxResult(success=True, stdout="OK", exit_code=0)

    def forbid(self, operation: str) -> None:
        self._forbidden_ops.append(operation)

    def set_timeout(self) -> None:
        self._timeout = True

    def reset(self) -> None:
        self._fixtures.clear()
        self._forbidden_ops.clear()
        self._timeout = False
