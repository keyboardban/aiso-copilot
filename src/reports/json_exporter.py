"""JSON export for the full audit result."""

import json
from pathlib import Path


def to_json_string(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


def export_json(result: dict, path) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_json_string(result), encoding="utf-8")
    return str(path)
