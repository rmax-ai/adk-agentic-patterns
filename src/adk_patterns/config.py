"""Configuration management for ADK Agentic Patterns.

Supports offline and live execution modes via environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class ExecutionMode(StrEnum):
    OFFLINE = "offline"
    LIVE = "live"


@dataclass
class Config:
    """Application configuration loaded from environment and defaults."""

    execution_mode: ExecutionMode = ExecutionMode.OFFLINE
    google_api_key: str | None = None
    google_cloud_project: str | None = None
    google_cloud_location: str = "us-central1"
    adk_model: str = "gemini-2.5-flash"
    verbose: bool = False
    trace: bool = False
    json_output: bool = False

    # Project paths
    project_root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2])
    examples_dir: Path = field(
        default_factory=lambda: Path(__file__).resolve().parents[2] / "examples"
    )

    @classmethod
    def from_env(cls) -> Config:
        """Load configuration from environment variables."""
        mode_str = os.getenv("PATTERNS_EXECUTION_MODE", "offline")
        try:
            mode = ExecutionMode(mode_str)
        except ValueError:
            mode = ExecutionMode.OFFLINE

        return cls(
            execution_mode=mode,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            google_cloud_project=os.getenv("GOOGLE_CLOUD_PROJECT"),
            google_cloud_location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
            adk_model=os.getenv("ADK_MODEL", "gemini-2.5-flash"),
        )

    @property
    def is_offline(self) -> bool:
        return self.execution_mode == ExecutionMode.OFFLINE

    @property
    def is_live(self) -> bool:
        return self.execution_mode == ExecutionMode.LIVE

    @property
    def has_live_credentials(self) -> bool:
        return bool(self.google_api_key)
