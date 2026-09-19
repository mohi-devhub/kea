"""Write backend/openapi.json (source for generated frontend types: `make types`)."""

import json
from pathlib import Path

from app.main import app

Path(__file__).resolve().parents[1].joinpath("openapi.json").write_text(
    json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
)
