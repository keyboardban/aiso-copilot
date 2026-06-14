"""Central configuration for AISO Copilot.

Free-first design: everything here works with zero API keys and no .env file.
All thresholds and weights live here so the scoring stays transparent and
matches SCORING_RUBRIC.md.
"""

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
SAMPLES_DIR = DATA_DIR / "samples"
OUTPUTS_DIR = ROOT_DIR / "outputs"
REPORTS_DIR = OUTPUTS_DIR / "reports"
WORKFLOWS_DIR = OUTPUTS_DIR / "workflows"
RUNS_DIR = OUTPUTS_DIR / "runs"

# .env is optional; missing python-dotenv (or missing .env) must never break anything.
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT_DIR / ".env")
except Exception:  # pragma: no cover - purely optional convenience
    pass


def get_env(name: str, default: str = "") -> str:
    value = os.environ.get(name, "")
    value = value.strip() if isinstance(value, str) else ""
    return value or default


# --- LLM modes ----------------------------------------------------------------
MODE_NO_LLM = "no_llm"
MODE_OPENROUTER = "openrouter"
MODE_OLLAMA = "ollama"
VALID_LLM_MODES = (MODE_NO_LLM, MODE_OPENROUTER, MODE_OLLAMA)

LLM_MODE_DEFAULT = get_env("LLM_MODE", MODE_NO_LLM).lower()
if LLM_MODE_DEFAULT not in VALID_LLM_MODES:
    LLM_MODE_DEFAULT = MODE_NO_LLM

OPENROUTER_API_KEY = get_env("OPENROUTER_API_KEY")
OPENROUTER_MODEL = get_env("OPENROUTER_MODEL")  # never hardcode a model here
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

OLLAMA_BASE_URL = get_env("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = get_env("OLLAMA_MODEL")

USE_EMBEDDINGS = get_env("AISO_USE_EMBEDDINGS", "0").lower() in {"1", "true", "yes"}
EMBEDDING_MODEL_NAME = get_env("AISO_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
# Recommended free model for cross-lingual (e.g. Thai page vs English question)
# semantic matching. Set AISO_EMBEDDING_MODEL to this when auditing across
# languages — the default all-MiniLM is English-centric (Check 4).
EMBEDDING_MODEL_MULTILINGUAL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# --- Fetching -----------------------------------------------------------------
REQUEST_TIMEOUT = 15
LLM_TIMEOUT = 60
USER_AGENT = "AISOCopilot/1.0 (free local AI Search readiness auditor)"
MAX_CONTENT_CHARS = 300_000  # safety cap for pasted/fetched content

# --- Chunking & retrieval -----------------------------------------------------
CHUNK_TARGET_WORDS = 110
CHUNK_MAX_WORDS = 170
TOP_K_EVIDENCE = 3

# Blend of deterministic signals for per-question coverage (sums to 1.0).
COVERAGE_WEIGHTS = {"term_overlap": 0.40, "tfidf": 0.35, "bm25": 0.25}
# Same, with optional local embeddings active.
COVERAGE_WEIGHTS_EMB = {"term_overlap": 0.30, "tfidf": 0.25, "bm25": 0.20, "embeddings": 0.25}
# Cross-lingual question (page language != question language) WITH embeddings:
# lean on semantic vector similarity, which is the only signal that bridges
# languages well (Check 4). Lexical signals stay as a small backstop.
COVERAGE_WEIGHTS_CROSSLINGUAL_EMB = {"term_overlap": 0.15, "tfidf": 0.10, "bm25": 0.10, "embeddings": 0.65}
BM25_SATURATION_K = 6.0  # bm25_sat = score / (score + K), maps raw BM25 to 0..1

# Coverage classification thresholds on the blended 0..1 score.
# Calibration note: template questions embed the topic phrase, so topic-only
# matches already land ~0.30-0.40 — PARTIAL therefore starts above that band,
# i.e. a question must match more than the page's general topic to count.
COVERED_THRESHOLD = 0.55
PARTIAL_THRESHOLD = 0.40

# --- Fan-out ------------------------------------------------------------------
MAX_FANOUT_QUESTIONS = 36
MAX_SEED_QUESTIONS = 30
ANSWER_SIM_MAX_QUESTIONS = 8

# --- Overall readiness weights (sum to 1.0; see SCORING_RUBRIC.md) -------------
READINESS_WEIGHTS = {
    "structure": 0.20,
    "entity_clarity": 0.15,
    "query_coverage": 0.25,
    "sourceability": 0.20,
    "schema": 0.10,
    "technical_extractability": 0.10,
}

# --- Search Console opportunity rules ------------------------------------------
SC_LOW_CTR = 1.5  # percent
SC_MIN_IMPRESSIONS = 500  # "high impressions" bar for the low-CTR rule
SC_STRIKING_DISTANCE = (8.0, 20.0)

PROJECT_NAME = "AISO Copilot"
PROJECT_SUBTITLE = (
    "A zero-cost AI Search audit platform for query fan-out coverage, sourceability "
    "scoring, content gap detection, schema recommendations, and client-ready audit reports."
)


def ensure_output_dirs(base: Path = None) -> dict:
    """Create output directories (idempotent) and return their paths."""
    base = Path(base) if base else OUTPUTS_DIR
    dirs = {
        "outputs": base,
        "reports": base / "reports",
        "workflows": base / "workflows",
        "runs": base / "runs",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs
