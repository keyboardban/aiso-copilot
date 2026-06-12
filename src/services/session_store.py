"""Persist analysis runs as local JSON files (free local storage, no database)."""

import json
from datetime import datetime
from pathlib import Path

from src.config import RUNS_DIR
from src.utils.text import slugify


def save_run(result: dict, runs_dir=None) -> str:
    runs_dir = Path(runs_dir) if runs_dir else RUNS_DIR
    runs_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    title = result.get("page", {}).get("title", "untitled")
    path = runs_dir / f"run_{stamp}_{slugify(title, 40)}.json"
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return str(path)


def list_runs(runs_dir=None) -> list:
    runs_dir = Path(runs_dir) if runs_dir else RUNS_DIR
    if not runs_dir.exists():
        return []
    entries = []
    for path in sorted(runs_dir.glob("run_*.json"), reverse=True):
        entry = {"file": str(path), "name": path.name, "title": "", "overall": None}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            entry["title"] = data.get("page", {}).get("title", "")
            entry["overall"] = data.get("scores", {}).get("overall_ai_search_readiness")
            entry["generated_at"] = data.get("generated_at", "")
        except Exception:
            pass
        entries.append(entry)
    return entries


def load_run(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
