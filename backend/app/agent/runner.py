"""Bounded investigation loop with grounding and a deterministic fallback."""

import json
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import ValidationError

from app.agent.grounding import validate_grounding
from app.agent.models import InvestigationResult, TraceEntry
from app.agent.templates import build_template_investigation
from app.agent.tools import ToolContext
from app.llm.base import LLMProvider
from app.llm.models import LLMRequest, Message, ToolCall, ToolSpec
from app.models.engine import Incident

StepCallback = Callable[[TraceEntry], Awaitable[None]]


def _submit_spec() -> ToolSpec:
    return ToolSpec(
        name="submit_investigation",
        description="Submit an evidence-cited investigation for the incident.",
        parameters={
            "type": "object",
            "required": ["summary", "root_cause_candidate_id", "narrative_steps"],
            "properties": {
                "summary": {"type": "string"},
                "root_cause_candidate_id": {"type": ["string", "null"]},
                "narrative_steps": {"type": "array"},
                "caveats": {"type": "array"},
                "disagreement": {"type": ["object", "null"]},
            },
        },
    )


class InvestigationAgent:
    def __init__(self, max_steps: int = 12) -> None:
        self.max_steps = max_steps

    async def investigate(
        self,
        incident: Incident,
        *,
        investigation_id: str | None = None,
        provider: LLMProvider | None = None,
        tool_context: ToolContext | None = None,
        on_step: StepCallback | None = None,
    ) -> InvestigationResult:
        investigation_id = investigation_id or f"INV-{uuid.uuid4().hex[:10]}"
        trace: list[TraceEntry] = []
        if provider is None:
            entry = TraceEntry(step=1, kind="template", name="deterministic-investigation")
            trace.append(entry)
            await self._emit(entry, on_step)
            return build_template_investigation(incident, investigation_id, trace=trace)

        tools = tool_context.registry() if tool_context else {}
        tool_specs = [item.spec for item in tools.values()] + [_submit_spec()]
        system = (
            "You are Kea's investigation agent. The deterministic engine ranking is authoritative. "
            "Use read-only tools, cite evidence IDs, do not invent probabilities, and submit a "
            "concise "
            "five-to-eight-step causal narrative. If you disagree with the ranking, explain why in "
            "disagreement rather than silently reranking."
        )
        messages = [
            Message(role="system", content=system),
            Message(
                role="user",
                content="Investigate this incident:\n"
                + json.dumps(incident.model_dump(mode="json"), sort_keys=True),
            ),
        ]
        for step in range(1, self.max_steps + 1):
            started = time.perf_counter()
            try:
                response = await provider.generate(
                    LLMRequest(
                        model=provider.model, messages=messages, tools=tool_specs, temperature=0.0
                    )
                )
            except Exception as exc:  # provider failures must never block template mode
                entry = TraceEntry(
                    step=step,
                    kind="error",
                    name="provider.generate",
                    result_summary=str(exc)[:240],
                    duration_ms=_elapsed_ms(started),
                )
                trace.append(entry)
                await self._emit(entry, on_step)
                return build_template_investigation(
                    incident,
                    investigation_id,
                    trace=trace,
                    caveats=[
                        f"Provider unavailable; used deterministic fallback ({type(exc).__name__})."
                    ],
                )
            model_entry = TraceEntry(
                step=step,
                kind="model",
                name="provider.generate",
                result_summary=response.finish_reason,
                duration_ms=_elapsed_ms(started),
            )
            trace.append(model_entry)
            await self._emit(model_entry, on_step)
            messages.append(response.message)
            if not response.tool_calls:
                break
            for call in response.tool_calls:
                if call.name == "submit_investigation":
                    try:
                        result = self._from_submission(
                            call, incident, investigation_id, response, trace, provider
                        )
                        failures = validate_grounding(result, incident)
                    except (ValidationError, TypeError, ValueError) as exc:
                        # a malformed submission is a grounding failure, never a crash
                        failures = [f"malformed submission: {type(exc).__name__}"]
                        result = None
                    if result is not None and not failures:
                        return result
                    repair = TraceEntry(
                        step=step,
                        kind="repair",
                        name="grounding.repair",
                        args_summary=json.dumps(failures),
                        result_summary="retrying once before template fallback",
                    )
                    trace.append(repair)
                    await self._emit(repair, on_step)
                    repaired = await self._repair(
                        provider,
                        messages,
                        call,
                        failures,
                        incident,
                        investigation_id,
                        trace,
                        on_step,
                        tool_specs,
                    )
                    if repaired is not None:
                        return repaired
                    return build_template_investigation(
                        incident,
                        investigation_id,
                        trace=trace,
                        caveats=["Provider output failed grounding; used deterministic fallback."],
                    )
                started_tool = time.perf_counter()
                if call.name not in tools:
                    tool_result = {"error": f"unknown or non-read-only tool: {call.name}"}
                else:
                    tool_result = tools[call.name].handler(call.arguments)
                entry = TraceEntry(
                    step=step,
                    kind="tool",
                    name=call.name,
                    args_summary=json.dumps(call.arguments, sort_keys=True)[:240],
                    result_summary=json.dumps(tool_result, sort_keys=True)[:320],
                    duration_ms=_elapsed_ms(started_tool),
                )
                trace.append(entry)
                await self._emit(entry, on_step)
                messages.append(
                    Message(
                        role="tool",
                        tool_call_id=call.id,
                        content=json.dumps(tool_result, sort_keys=True),
                    )
                )
        return build_template_investigation(
            incident,
            investigation_id,
            trace=trace,
            caveats=[
                "Provider did not submit a grounded investigation; used deterministic fallback."
            ],
        )

    async def _repair(
        self,
        provider: LLMProvider,
        messages: list[Message],
        call: ToolCall,
        failures: list[str],
        incident: Incident,
        investigation_id: str,
        trace: list[TraceEntry],
        on_step: StepCallback | None,
        tool_specs: list[ToolSpec],
    ) -> InvestigationResult | None:
        messages = list(messages)
        messages.append(
            Message(
                role="tool",
                tool_call_id=call.id,
                content=json.dumps({"grounding_errors": failures}),
            )
        )
        started = time.perf_counter()
        try:
            response = await provider.generate(
                LLMRequest(
                    model=provider.model, messages=messages, tools=tool_specs, temperature=0.0
                )
            )
        except Exception as exc:
            entry = TraceEntry(
                step=len(trace) + 1,
                kind="error",
                name="grounding.repair",
                result_summary=str(exc)[:240],
            )
            trace.append(entry)
            await self._emit(entry, on_step)
            return None
        entry = TraceEntry(
            step=len(trace) + 1,
            kind="model",
            name="grounding.repair",
            result_summary=response.finish_reason,
            duration_ms=_elapsed_ms(started),
        )
        trace.append(entry)
        await self._emit(entry, on_step)
        for repaired_call in response.tool_calls:
            if repaired_call.name != "submit_investigation":
                continue
            try:
                result = self._from_submission(
                    repaired_call, incident, investigation_id, response, trace, provider
                )
            except (ValidationError, TypeError, ValueError):
                continue
            if not validate_grounding(result, incident):
                return result
        return None

    @staticmethod
    def _from_submission(
        call: ToolCall,
        incident: Incident,
        investigation_id: str,
        response: Any,
        trace: list[TraceEntry],
        provider: LLMProvider,
    ) -> InvestigationResult:
        fallback = build_template_investigation(incident, investigation_id)
        allowed = fallback.model_dump(mode="python")
        for key in (
            "summary",
            "root_cause_candidate_id",
            "narrative_steps",
            "caveats",
            "disagreement",
        ):
            if key in call.arguments:
                allowed[key] = call.arguments[key]
        allowed["mode"] = "REPLAYED" if getattr(provider, "mode", "") == "replay" else "LIVE"
        allowed["provider"] = str(getattr(provider, "name", response.provider))
        allowed["model"] = str(getattr(provider, "model", response.model))
        allowed["trace"] = trace
        usage = response.usage or {}
        allowed["usage"] = {
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "total_tokens": usage.get("total_tokens"),
        }
        return InvestigationResult.model_validate(allowed)

    @staticmethod
    async def _emit(entry: TraceEntry, callback: StepCallback | None) -> None:
        if callback is not None:
            await callback(entry)


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))
