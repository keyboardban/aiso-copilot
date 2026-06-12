"""Loads bundled sample data so the full demo works offline with no API keys."""

import json
from pathlib import Path

from src.config import SAMPLES_DIR


def list_samples() -> list:
    """Names of analyzable sample pages (markdown/html) in data/samples/."""
    if not SAMPLES_DIR.exists():
        return []
    return sorted(
        p.name for p in SAMPLES_DIR.iterdir() if p.suffix.lower() in (".md", ".html")
    )


def load_sample(name: str) -> dict:
    """Return {name, content, source_type} for a bundled sample page."""
    path = SAMPLES_DIR / Path(name).name  # Path(name).name blocks traversal
    if not path.exists():
        raise FileNotFoundError(f"Sample '{name}' not found in {SAMPLES_DIR}")
    source_type = "html" if path.suffix.lower() == ".html" else "markdown"
    return {
        "name": path.name,
        "content": path.read_text(encoding="utf-8"),
        "source_type": source_type,
    }


def load_seed_questions() -> list:
    path = SAMPLES_DIR / "seed_questions.txt"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip()]


def load_competitors() -> dict:
    path = SAMPLES_DIR / "competitors_sample.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def sample_search_console_path() -> Path:
    return SAMPLES_DIR / "search_console_sample.csv"


def demo_defaults() -> dict:
    """Everything the demo mode needs, pulled from bundled sample data."""
    competitors = load_competitors()
    return {
        "sample_name": "sample_page.md",
        "target_topic": competitors.get("topic", "AI Search Optimization"),
        "target_audience": competitors.get(
            "target_audience", "Thai businesses looking for AI Search services"
        ),
        "brand": competitors.get("brand", ""),
        "market": competitors.get("market", ""),
        "seed_questions": load_seed_questions(),
        "search_console_csv": str(sample_search_console_path()),
    }
