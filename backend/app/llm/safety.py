"""Outbound guard: nothing that looks like a secret or personal path leaves the machine.

Every live provider call is wrapped in `SafeProvider`. Only simulated telemetry, engine output and
evidence are meant to be sent; this is the backstop if anything else ever ends up in a prompt.
Error messages name the pattern that matched, never the matched text.
"""

import re

from app.llm.base import LLMError, LLMProvider
from app.llm.models import LLMRequest, LLMResponse

_PATTERNS: dict[str, re.Pattern[str]] = {
    "api key (sk-...)": re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"),
    "cloud access key id": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "github token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "bearer token": re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{20,}"),
    "home directory path": re.compile(r"(?:/Users|/home)/[A-Za-z0-9._\-]+/"),
}


def find_secret(text: str, secrets: list[str]) -> str | None:
    """Return a description of what looks unsafe in `text`, or None."""
    for value in secrets:
        if value and value in text:
            return "a configured API key"
    for label, pattern in _PATTERNS.items():
        if pattern.search(text):
            return label
    return None


class SafeProvider:
    """Wraps a real provider and refuses requests that appear to contain secrets."""

    def __init__(self, provider: LLMProvider, secrets: list[str]) -> None:
        self.provider = provider
        self.secrets = secrets
        self.name = provider.name
        self.model = provider.model

    async def generate(self, request: LLMRequest) -> LLMResponse:
        problem = find_secret(request.model_dump_json(), self.secrets)
        if problem is not None:
            raise LLMError(f"blocked outbound request: it appears to contain {problem}")
        return await self.provider.generate(request)
