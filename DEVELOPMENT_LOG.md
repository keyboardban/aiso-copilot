# Development Log

Reverse-ordered milestones. Each entry: what was implemented, decisions made, known
issues, next steps.

---

## 2026-06-12 — M8 · Final verification & documentation

**Implemented:** README, PIPELINE_AND_ARCHITECTURE, SCORING_RUBRIC,
MODEL_AND_LIMITATIONS finalized against the actual code (weights, thresholds, and
check tables match the implementation). Full verification pass: 32/32 tests green;
CLI demo, all six FastAPI endpoints, and the complete Streamlit flow (AppTest:
analyze click + all 11 tabs) verified with zero API keys and no network.

**Decisions:** documentation states honest limitations prominently (estimated
readiness, no ranking/citation claims) per spec §3/§18.

**Known issues:** none blocking. See "Known approximations" in MODEL_AND_LIMITATIONS.

**Next steps (post-MVP ideas):** multi-page site audits; before/after re-audit diffing;
optional embedding mode docs with a benchmark; competitor page side-by-side coverage.

## 2026-06-12 — M7 · Streamlit dashboard + FastAPI backend + tests

**Implemented:** `app/streamlit_app.py` (sidebar with 3 input modes, topic/audience/
seeds, CSV upload, 3 LLM modes with conditional fields; 11 tabs incl. scorecards,
radar chart, evidence expanders, simulated answers, 4 download buttons).
`api/server.py` with `/health`, `/analyze`, `/fanout`, `/coverage`,
`/schema/recommend`, `/report/generate`. Test suite: 6 files / 32 tests (fan-out,
coverage, scoring, schema, LLM fallback, end-to-end demo).

**Decisions:** downloads served from memory (works on ephemeral hosting); API defaults
to `write_files=False`; AppTest used to exercise the full UI flow headlessly.

**Issues found & fixed:** corrupted emoji in tab label; Arrow serialization warning
(mixed int/str column in Entities tab); Streamlit `use_container_width` deprecation.

## 2026-06-12 — M6 · Calibration pass on the sample corpus

**Implemented:** ran the full pipeline on the bundled samples and tuned: coverage
thresholds (Partial floor 0.28 → **0.40**, with rationale documented — topic-phrase
matches alone reach ~0.30–0.40 and must not count as Partial), Search Console
high-impression bar 200 → **500** so mid-tier rows fall through to striking-distance /
question rules (one primary opportunity per row, precedence-ordered, secondary signals
annotated), answer-simulation heading leak fixed (truncation collapses newlines →
prefix-strip).

**Result:** demo distribution 13 Covered / 17 Partial / 1 Missing on the .md sample;
md vs html samples differentiate exactly as designed (schema 30 vs 77 — the html
variant ships partial Organization JSON-LD).

## 2026-06-12 — M5 · Reports, Search Console, n8n, services

**Implemented:** markdown report builder (all 14 spec sections, escaped tables, score
bands), JSON exporter, GSC CSV loader (lenient column aliases, %-string CTR,
fraction-CTR normalization), opportunity rules (intent_mismatch,
high_impression_low_ctr, low_ctr_despite_rank, striking_distance,
ai_answer_opportunity), n8n blueprint generator (readable node list + n8n-style import
skeleton + safety notes), metrics (Flesch with Thai-aware skip), session store,
and the `run_analysis()` orchestrator with CLI entry point.

**Decisions:** executive summary is template-built then optionally LLM-polished;
`report_markdown` returned in-memory but excluded from `audit_result.json`;
answer simulation lives inside the analyzer (consumes coverage + LLM handle).

## 2026-06-12 — M4 · LLM layer (optional by construction)

**Implemented:** provider base (`complete() → str | None`, never raises),
no-LLM provider (always available, always returns None → template path),
OpenRouter provider (user-supplied key + slug, every error class caught and recorded
in `last_error`), Ollama provider (reachability ping, auto-picks first installed
model), prompt builders (fan-out extras, grounded answer simulation with explicit
MISSING line, summary polish), `get_provider()` resolution with explanatory status
strings.

**Decisions:** no model slug hardcoded anywhere; LLM restricted to additive polish;
entity extraction kept deterministic-only (entities feed core scoring — spec allowed
LLM refinement, deliberately skipped for reproducibility).

## 2026-06-12 — M3 · Audit layer

**Implemented:** entity extractor (JSON-LD names, title/domain brand fallback, curated
bilingual lexicons, sentence patterns; 11 weighted categories = 100), structure audit
(24 checks, total weight 120, per-check details + recommendations), sourceability
(15 evidence checks = 100, each failure explains why it matters for citation), schema
recommender (content-gated types, JSON-LD preview strictly from visible content,
LocalBusiness requires visible NAP, spec-required warning string included), scoring
combiner (weighted overall, headroom-ranked priority actions).

## 2026-06-12 — M2 · Retrieval & fan-out

**Implemented:** section-based chunker (heading-prefixed passages, ~110-word target),
BM25 retriever (rank-bm25 + pure-Python Okapi twin), TF-IDF retriever (sklearn +
pure-Python twin, shared analyzer), opt-in embedding retriever, hybrid coverage
(0.40 overlap / 0.35 tfidf / 0.25 bm25-saturated, evidence snippets, missing-term gap
explanations, intent-keyed recommendations), 20 spec templates + entity-aware extras,
bilingual intent rule cascade (11 intents), fan-out generator (seeds → templates →
entity extras → optional LLM extras, deduped).

**Decisions:** Thai handled with character trigrams in one shared tokenizer;
`"seed"` added to the fan-out source enum (documented spec extension); pure-Python
retrieval fallbacks added beyond spec so a partial install still works.

## 2026-06-12 — M1 · Foundation: structure, samples, extraction

**Implemented:** repo structure (per spec §8, built at the working-directory root —
documented deviation), requirements (core + optional local), `.env.example`
(`LLM_MODE=no_llm` default), `.gitignore`, sample data (intentionally imperfect
bilingual service page in .md and .html variants — the html one with deliberately
partial Organization JSON-LD and no FAQPage despite visible FAQ; 8 Thai seed
questions; 30-row realistic GSC CSV; competitors JSON), config (all weights/thresholds
centralized), Thai-aware tokenizer, validators, sample loader, fetcher (structured
failures + paste-mode suggestion), JSON-LD/microdata parser, and the content extractor
(HTML via BS4/lxml with optional trafilatura, Markdown with frontmatter, plain text;
sections, links, FAQ/Q&A detection, technical-extractability scoring).

**Environment:** Python 3.14.2, venv at `.venv/`, all requirements installed free.
