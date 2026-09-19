"""Provider selection: which adapter serves which role, and what happens when none is usable.

A provider only activates when its name, a model and a key are all configured. Anything else
returns an `UnavailableProvider` whose error becomes an honest caveat on a template fallback.
"""

from typing import Any, cast

from app.llm.base import LLMError, LLMProvider
from app.llm.cache import CachedProvider, CacheMode
from app.llm.models import LLMRequest, LLMResponse
from app.llm.openai_adapter import OpenAIProvider
from app.llm.safety import SafeProvider

_TEMPLATE = {"", "template", "none", "fake"}


class UnavailableProvider:
    def __init__(self, name: str, model: str, reason: str = "not configured") -> None:
        self.name = name
        self.model = model
        self.reason = reason

    async def generate(self, _: LLMRequest) -> LLMResponse:
        raise LLMError(f"{self.name} provider unavailable: {self.reason}")


def provider_for_settings(settings: Any, role: str = "agent") -> LLMProvider | None:
    """Return the provider for a role ("agent", "baseline", "fix"), or None for template mode."""
    name = (getattr(settings, f"{role}_llm_provider", "") or settings.llm_provider).strip().lower()
    model = (getattr(settings, f"{role}_llm_model", "") or settings.llm_model).strip()
    if name in _TEMPLATE:
        return None
    provider: LLMProvider
    if model in {"", "CHANGE_ME"}:
        provider = UnavailableProvider(name, model, "no model configured (set LLM_MODEL)")
    elif name == "openai":
        key = settings.openai_api_key
        if key is None or not key.get_secret_value():
            provider = UnavailableProvider(name, model, "OPENAI_API_KEY is not set")
        else:
            provider = SafeProvider(
                OpenAIProvider(
                    key.get_secret_value(),
                    model,
                    effort=settings.llm_reasoning_effort,
                    max_output_tokens=settings.llm_max_output_tokens,
                    timeout_s=settings.llm_timeout_s,
                ),
                settings.secret_values(),
            )
    else:
        provider = UnavailableProvider(name, model, "adapter not implemented yet")
    mode = str(settings.llm_cache_mode).strip().lower()
    if mode in {"record", "replay"}:
        return cast(
            LLMProvider, CachedProvider(provider, settings.llm_cache_dir, cast(CacheMode, mode))
        )
    return provider
