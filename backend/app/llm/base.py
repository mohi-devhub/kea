"""Provider protocol and errors."""

from typing import Protocol

from app.llm.models import LLMRequest, LLMResponse


class LLMError(RuntimeError):
    """A provider was unavailable or returned an unusable response."""


class CacheMiss(LLMError):
    """Replay mode was asked for a request that has no recorded response."""


class LLMProvider(Protocol):
    name: str
    model: str

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate one response for a normalized request."""
