"""Write backend/openapi.json (source for generated frontend types: `make types`).

Routes that return plain dicts leave engine and WS models out of the OpenAPI document, so the
contract models are merged into `components.schemas` explicitly. This is what gives the frontend
generated `Incident`, `Candidate`, `Prediction` and `WsEnvelope` types instead of hand-drifted ones.
"""

import json
from pathlib import Path

from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from app.agent.models import InvestigationResult, TraceEntry
from app.main import app
from app.models.api import ErrorResponse, WsEnvelope
from app.models.engine import (
    Anomaly,
    Candidate,
    EngineUpdate,
    Evidence,
    Incident,
    Prediction,
    PredictionVerification,
    RejectedCandidate,
    WhatChanged,
)

CONTRACT_MODELS: list[type[BaseModel]] = [
    Anomaly, Candidate, EngineUpdate, ErrorResponse, Evidence, Incident, Prediction,
    PredictionVerification, RejectedCandidate, WhatChanged, WsEnvelope,
    InvestigationResult, TraceEntry,
]  # fmt: skip

spec = app.openapi()
_, extra = models_json_schema(
    [(model, "serialization") for model in CONTRACT_MODELS],
    ref_template="#/components/schemas/{model}",
)
schemas = spec.setdefault("components", {}).setdefault("schemas", {})
for name, schema in extra.get("$defs", {}).items():
    schemas.setdefault(name, schema)

Path(__file__).resolve().parents[1].joinpath("openapi.json").write_text(
    json.dumps(spec, indent=2, sort_keys=True) + "\n"
)
