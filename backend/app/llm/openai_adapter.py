"""OpenAI adapter, written against the Responses API (the API current models are served on).

Design notes, from the OpenAI function-calling guide:
- Stateless: `store=False`, so OpenAI keeps no copy of the conversation. Prior output items
  (reasoning and function_call items) are echoed back on the next turn via `Message.raw`, with
  `include=["reasoning.encrypted_content"]` so reasoning items can be passed back.
- `temperature` is not sent: reasoning models restrict it. Determinism comes from the engine, not
  from the model; the agent only explains.
- Errors are reduced to the class name and HTTP status. Some API errors echo part of the key.
"""

import json
from typing import Any

import openai
from openai import AsyncOpenAI

from app.llm.base import LLMError
from app.llm.models import LLMRequest, LLMResponse, Message, ToolCall


def _loads(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {"_invalid_arguments": raw[:200]}
    return value if isinstance(value, dict) else {"_invalid_arguments": raw[:200]}


class OpenAIProvider:
    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        effort: str = "low",
        max_output_tokens: int = 4000,
        timeout_s: float = 60.0,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self.model = model
        self.effort = effort
        self.max_output_tokens = max_output_tokens
        self._client = client or AsyncOpenAI(api_key=api_key, timeout=timeout_s, max_retries=2)

    @staticmethod
    def _input_items(messages: list[Message]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for message in messages:
            if message.role == "system":
                continue  # sent as `instructions`
            if message.role == "user":
                items.append({"role": "user", "content": message.content})
            elif message.role == "assistant":
                if message.raw:
                    items.extend(message.raw)  # native items from the previous turn
                    continue
                if message.content:
                    items.append({"role": "assistant", "content": message.content})
                for call in message.tool_calls:
                    items.append(
                        {
                            "type": "function_call",
                            "call_id": call.id,
                            "name": call.name,
                            "arguments": json.dumps(call.arguments),
                        }
                    )
            elif message.role == "tool":
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": message.tool_call_id or "",
                        "output": message.content,
                    }
                )
        return items

    async def generate(self, request: LLMRequest) -> LLMResponse:
        instructions = "\n\n".join(m.content for m in request.messages if m.role == "system")
        kwargs: dict[str, Any] = {
            "model": request.model or self.model,
            "input": self._input_items(request.messages),
            "store": False,
            "include": ["reasoning.encrypted_content"],
            "max_output_tokens": request.max_tokens or self.max_output_tokens,
            "reasoning": {"effort": self.effort},
        }
        if instructions:
            kwargs["instructions"] = instructions
        if request.tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {"type": "object", "properties": {}, **tool.parameters},
                    "strict": False,
                }
                for tool in request.tools
            ]
            kwargs["tool_choice"] = request.tool_choice
        try:
            response = await self._client.responses.create(**kwargs)
        except openai.APIStatusError as exc:
            raise LLMError(f"OpenAI request failed (HTTP {exc.status_code})") from None
        except openai.OpenAIError as exc:
            raise LLMError(f"OpenAI request failed ({type(exc).__name__})") from None

        tool_calls: list[ToolCall] = []
        text_parts: list[str] = []
        for item in response.output:
            if item.type == "function_call":
                tool_calls.append(
                    ToolCall(id=item.call_id, name=item.name, arguments=_loads(item.arguments))
                )
            elif item.type == "message":
                text_parts.extend(c.text for c in item.content if c.type == "output_text")
        incomplete = getattr(response.incomplete_details, "reason", None)
        finish = "tool_calls" if tool_calls else ("length" if incomplete else "stop")
        usage: dict[str, int | float] = {}
        if response.usage is not None:
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.total_tokens,
                "reasoning_tokens": response.usage.output_tokens_details.reasoning_tokens,
            }
        return LLMResponse(
            message=Message(
                role="assistant",
                content="".join(text_parts),
                tool_calls=tool_calls,
                raw=[item.model_dump(mode="json", exclude_none=True) for item in response.output],
            ),
            finish_reason=finish,
            usage=usage,
            provider=self.name,
            model=str(response.model),
        )
