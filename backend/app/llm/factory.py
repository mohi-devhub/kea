"""Provider selection boundary.

Actual hosted-provider adapters are intentionally opt-in.  Until one is
configured, the agent remains fully useful through deterministic template mode.
"""

from typing import Any, cast

from app.llm.base import LLMError
from app.llm.cache import CachedProvider, CacheMode
from app.llm.models import LLMRequest, LLMResponse


class UnavailableProvider:
    def __init__(self, name: str, model: str) -> None:
        self.name = name
        self.model = model

    async def generate(self, _: LLMRequest) -> LLMResponse:
        raise LLMError(f"{self.name} provider adapter is not configured")


def provider_for_settings(settings: Any) -> object | None:
    name = str(settings.llm_provider).strip().lower()
    if name in {"", "template", "none", "fake"}:
        return None
    provider: object = UnavailableProvider(name, str(settings.llm_model))
    mode = str(settings.llm_cache_mode).strip().lower()
    if mode in {"off", "record", "replay"} and mode != "off":
        provider = CachedProvider(provider, settings.llm_cache_dir, cast(CacheMode, mode))
    return provider
