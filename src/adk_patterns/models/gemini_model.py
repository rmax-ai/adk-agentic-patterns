"""Gemini model adapter for live execution mode.

Only loaded when PATTERNS_EXECUTION_MODE=live and GOOGLE_API_KEY is set.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from adk_patterns.config import Config

from adk_patterns.errors import ModelError


class GeminiAdapter:
    """Adapter for live Gemini model execution via google-genai."""

    def __init__(self, config: Config) -> None:
        if not config.google_api_key:
            raise ModelError(
                "GOOGLE_API_KEY not set. Set it or use PATTERNS_EXECUTION_MODE=offline."
            )
        self.config = config
        self._client: Any = None

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                from google import genai

                self._client = genai.Client(api_key=self.config.google_api_key)
            except ImportError as err:
                raise ModelError("google-genai not installed. Run: uv sync") from err
        return self._client

    def get_model_name(self) -> str:
        return self.config.adk_model
