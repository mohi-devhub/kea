"""Content-addressed record/replay wrapper for provider calls."""

import hashlib
import json
from pathlib import Path
from typing import Literal

from app.llm.base import CacheMiss
from app.llm.models import LLMRequest, LLMResponse

CacheMode = Literal["off", "record", "replay"]


class CachedProvider:
    def __init__(self, provider: object, directory: Path, mode: CacheMode) -> None:
        self.provider = provider
        self.directory = directory
        self.mode = mode
        self.name = str(getattr(provider, "name", "unknown"))
        self.model = str(getattr(provider, "model", "unknown"))

    def key(self, request: LLMRequest) -> str:
        payload = json.dumps(
            {
                "provider": self.name,
                "model": self.model,
                "request": request.model_dump(mode="json"),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _path(self, request: LLMRequest) -> Path:
        return self.directory / f"{self.key(request)}.json"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        path = self._path(request)
        if self.mode == "replay":
            if not path.exists():
                raise CacheMiss(f"no recorded LLM response for request {path.stem}")
            response = LLMResponse.model_validate_json(path.read_text(encoding="utf-8"))
            return response
        response = await self.provider.generate(request)  # type: ignore[attr-defined]
        response = LLMResponse.model_validate(response)
        if self.mode == "record":
            self.directory.mkdir(parents=True, exist_ok=True)
            path.write_text(response.model_dump_json(indent=2), encoding="utf-8")
        return response
