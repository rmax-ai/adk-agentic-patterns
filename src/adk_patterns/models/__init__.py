"""Model protocol and scripted (fake) model adapter.

The scripted model enables fully deterministic offline testing. It participates
through the same orchestration paths as a real model by implementing a minimal
LLM interface compatible with ADK's model integration points.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ModelResponse:
    """A simulated model response. Mirrors the shape ADK expects from an LLM call."""

    text: str = ""
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    structured_output: dict[str, Any] | None = None
    finish_reason: str = "stop"
    usage: TokenUsage = field(default_factory=lambda: TokenUsage())


@dataclass
class ToolCallRequest:
    """A tool call the model requests the runtime to execute."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class TokenUsage:
    """Synthetic token usage for cost tracking."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class ModelInvocation:
    """Record of a single model invocation for audit and debugging."""

    call_index: int
    system_instruction: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    response: ModelResponse | None = None
    error: str | None = None
    latency_ms: float = 0.0


class FixtureKey(str):
    """Marker for fixture-driven responses.

    Fixture keys map to predefined responses in the scripted model's fixture store.
    """

    pass


class ScriptedModel:
    """A deterministic fake model for offline testing.

    Returns predefined responses based on fixture keys embedded in the conversation.
    Does not bypass ADK — it implements the same interface and is invoked through
    the same callbacks and orchestration paths as a real model.

    Features:
    - Fixture-keyed responses
    - Structured output emission
    - Tool call simulation
    - Malformed response simulation
    - Latency simulation
    - Error simulation (transient and permanent)
    - Non-convergence simulation
    - Full invocation recording
    - Synthetic token usage reporting
    """

    def __init__(self) -> None:
        self._fixtures: dict[str, ModelResponse] = {}
        self._invocations: list[ModelInvocation] = []
        self._call_count: int = 0
        self._error_on_call: dict[int, Exception] = {}
        self._latency_ms: float = 0.0
        self._repeat_response: ModelResponse | None = None
        self._response_sequence: list[ModelResponse] = []

    # -- Fixture management --

    def register_fixture(self, key: str, response: ModelResponse) -> None:
        """Register a fixture response for a given key."""
        self._fixtures[key] = response

    def register_fixtures(self, fixtures: dict[str, ModelResponse]) -> None:
        """Register multiple fixtures at once."""
        self._fixtures.update(fixtures)

    # -- Error injection --

    def inject_error_on_call(self, call_index: int, error: Exception) -> None:
        """Make the Nth call raise the given exception (transient error)."""
        self._error_on_call[call_index] = error

    def set_permanent_error(self, error: Exception) -> None:
        """Make ALL subsequent calls raise the given exception."""
        self._repeat_response = None
        self._response_sequence = []
        self._error_on_call = {i: error for i in range(100)}

    # -- Latency simulation --

    def set_latency(self, ms: float) -> None:
        """Add simulated latency to every call."""
        self._latency_ms = ms

    # -- Response control --

    def set_response_sequence(self, responses: list[ModelResponse]) -> None:
        """Return responses in order, then repeat the last one."""
        self._response_sequence = list(responses)
        self._repeat_response = None

    def set_repeat_response(self, response: ModelResponse) -> None:
        """Return the same response for every call."""
        self._repeat_response = response
        self._response_sequence = []

    def set_non_converging(self, response: ModelResponse) -> None:
        """Return the same response forever (simulates non-convergence)."""
        self._repeat_response = response
        self._response_sequence = []

    # -- Fixture key extraction --

    @staticmethod
    def extract_fixture_key(messages: list[dict[str, Any]]) -> str | None:
        """Scan messages for a fixture key marker.

        Fixture keys are embedded as: __FIXTURE__:key_name
        """
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str) and "__FIXTURE__:" in content:
                return content.split("__FIXTURE__:")[1].split()[0].strip(":")
        return None

    # -- Invocation recording --

    @property
    def invocations(self) -> list[ModelInvocation]:
        return list(self._invocations)

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def total_tokens(self) -> int:
        return sum(inv.response.usage.total_tokens for inv in self._invocations if inv.response)

    def reset(self) -> None:
        """Reset all state for a fresh test."""
        self._fixtures.clear()
        self._invocations.clear()
        self._call_count = 0
        self._error_on_call.clear()
        self._latency_ms = 0.0
        self._repeat_response = None
        self._response_sequence.clear()

    # -- Core invoke method --

    def invoke(
        self,
        system_instruction: str = "",
        messages: list[dict[str, Any]] | None = None,
        tools: list[dict[str, Any]] | None = None,
        response_schema: type | dict[str, Any] | None = None,
    ) -> ModelResponse:
        """Invoke the scripted model.

        Resolution order:
        1. Error injection (if this call index has an injected error)
        2. Response sequence (if configured)
        3. Repeat response (if configured)
        4. Fixture key lookup
        5. Default empty response
        """
        messages = messages or []
        self._call_count += 1
        call_index = self._call_count

        invocation = ModelInvocation(
            call_index=call_index,
            system_instruction=system_instruction,
            messages=messages,
        )
        self._invocations.append(invocation)

        # Check for injected errors
        if call_index in self._error_on_call:
            error = self._error_on_call[call_index]
            invocation.error = str(error)
            logger.warning("scripted_model.error_injected", call=call_index, error=str(error))
            raise error

        # Return from response sequence
        if self._response_sequence:
            idx = min(call_index - 1, len(self._response_sequence) - 1)
            response = self._response_sequence[idx]
            invocation.response = response
            return response

        # Return repeat response
        if self._repeat_response:
            invocation.response = self._repeat_response
            return self._repeat_response

        # Look up fixture key
        fixture_key = self.extract_fixture_key(messages)
        if fixture_key and fixture_key in self._fixtures:
            response = self._fixtures[fixture_key]
            invocation.response = response
            return response

        # Default: empty response
        response = ModelResponse(
            text="",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=0, total_tokens=10),
        )
        invocation.response = response
        return response

    # -- ADK integration helpers --

    def as_adk_model_callback(self) -> Callable:
        """Return a before_model_callback suitable for ADK LlmAgent.

        This callback intercepts model calls and returns the scripted response,
        so the ADK orchestration path (tool calls, state management) runs
        exactly as it would with a live model.
        """

        async def callback(
            context: Any,  # adk.agents.Context
            llm_request: Any,  # adk.models.LlmRequest
        ) -> Any | None:
            from google.adk.models.llm_response import LlmResponse

            messages_raw = []
            if hasattr(llm_request, "contents"):
                for c in llm_request.contents:
                    if hasattr(c, "parts"):
                        for p in c.parts:
                            if hasattr(p, "text") and p.text:
                                messages_raw.append({"role": getattr(c, "role", "user"), "content": p.text})

            try:
                response = self.invoke(
                    system_instruction=getattr(llm_request, "system_instruction", ""),
                    messages=messages_raw,
                )
                invocation = self._invocations[-1]
                invocation.latency_ms = self._latency_ms

                # Build LlmResponse
                from google.genai.types import Content, Part

                parts = []
                if response.text:
                    parts.append(Part(text=response.text))
                if response.structured_output:
                    import json
                    parts.append(Part(text=json.dumps(response.structured_output)))

                llm_response = LlmResponse(
                    content=Content(role="model", parts=parts) if parts else None,
                )
                return llm_response

            except Exception as e:
                invocation = self._invocations[-1] if self._invocations else None
                if invocation:
                    invocation.error = str(e)
                raise

        return callback


# -- Convenience factories --


def text_response(text: str, prompt_tokens: int = 100, completion_tokens: int = 50) -> ModelResponse:
    """Create a simple text response."""
    return ModelResponse(
        text=text,
        usage=TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


def tool_call_response(
    tool_name: str,
    arguments: dict[str, Any],
    call_id: str = "call_001",
) -> ModelResponse:
    """Create a response that requests a tool call."""
    return ModelResponse(
        tool_calls=[ToolCallRequest(id=call_id, name=tool_name, arguments=arguments)],
        usage=TokenUsage(prompt_tokens=100, completion_tokens=30, total_tokens=130),
    )


def structured_response(
    data: dict[str, Any],
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
) -> ModelResponse:
    """Create a response with structured output."""
    return ModelResponse(
        structured_output=data,
        usage=TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


def error_response(error_text: str) -> ModelResponse:
    """Create a malformed/error response for testing error handling."""
    return ModelResponse(
        text=error_text,
        finish_reason="error",
        usage=TokenUsage(prompt_tokens=50, completion_tokens=10, total_tokens=60),
    )
