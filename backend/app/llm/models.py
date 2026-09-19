"""Small, provider-neutral LLM request/response models.

The agent never imports an SDK-specific message type.  Adapters can translate
these models to a provider's wire format without changing the agent loop.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None


class LLMRequest(BaseModel):
    model: str
    messages: list[Message]
    tools: list[ToolSpec] = Field(default_factory=list)
    tool_choice: str = "auto"
    temperature: float = 0.0
    max_tokens: int | None = None


class LLMResponse(BaseModel):
    message: Message
    finish_reason: Literal["stop", "tool_calls", "length", "error"] = "stop"
    usage: dict[str, int | float] = Field(default_factory=dict)
    provider: str = "unknown"
    model: str = "unknown"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def tool_calls(self) -> list[ToolCall]:
        return self.message.tool_calls
