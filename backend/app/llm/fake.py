"""Deterministic provider for tests, local demos, and replay fixtures."""

from collections import deque
from collections.abc import Iterable

from app.llm.base import LLMError
from app.llm.models import LLMRequest, LLMResponse, Message


class FakeProvider:
    name = "fake"

    def __init__(self, responses: Iterable[LLMResponse] = (), model: str = "fake-v1") -> None:
        self.model = model
        self._responses = deque(responses)
        self.requests: list[LLMRequest] = []

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if not self._responses:
            raise LLMError("FakeProvider has no scripted response")
        response = self._responses.popleft()
        return response.model_copy(update={"provider": self.name, "model": self.model})


def text_response(content: str, *, model: str = "fake-v1") -> LLMResponse:
    """Convenience helper for tests that only need an assistant message."""

    return LLMResponse(
        message=Message(role="assistant", content=content),
        provider="fake",
        model=model,
    )
