"""Strict parser for baseline JSON responses."""

import json
import re
from typing import Any

from pydantic import ValidationError

from app.eval.models import BaselineAnswer, RerankAnswer

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


def parse_output(raw: str) -> BaselineAnswer:
    candidate = raw.strip()
    fenced = _FENCE.match(candidate)
    if fenced:
        candidate = fenced.group(1).strip()
    value: Any = json.loads(candidate)
    try:
        return BaselineAnswer.model_validate(value)
    except ValidationError as exc:
        raise ValueError("baseline output does not match the JSON contract") from exc


def parse_rerank_output(raw: str) -> RerankAnswer:
    candidate = raw.strip()
    fenced = _FENCE.match(candidate)
    if fenced:
        candidate = fenced.group(1).strip()
    value: Any = json.loads(candidate)
    try:
        return RerankAnswer.model_validate(value)
    except ValidationError as exc:
        raise ValueError("reranker output does not match the JSON contract") from exc
