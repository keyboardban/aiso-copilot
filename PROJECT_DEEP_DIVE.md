# AISO Copilot — Engineering Deep Dive

A single narrative that ties the whole project together: what it is, how it
works, what we've improved, the problems we solved and still face, how we
evaluate it, why it's a credible *simulation* of answer-engine retrieval (and
where it isn't), the roadmap, and an interview script for presenting it.

This is the "explain it to a smart engineer in 15 minutes" document. For
specifics see: [README](README.md) · [PIPELINE_AND_ARCHITECTURE](PIPELINE_AND_ARCHITECTURE.md)
· [SCORING_RUBRIC](SCORING_RUBRIC.md) · [MODEL_AND_LIMITATIONS](MODEL_AND_LIMITATIONS.md)
· [evals/FINDINGS](evals/FINDINGS.md) · [USER_GUIDE](USER_GUIDE.md).

---

## 1. What it is, in one paragraph

**AISO Copilot** audits whether a webpage is ready to be understood, retrieved,
and cited by AI-assisted search / answer engines (Google AI Overviews,
ChatGPT-search, Perplexity-style systems). It ingests a page the way a RAG system
would — parse → chunk → index — then runs a generated "query fan-out" question set
against that index and scores, with evidence, how well the page can answer each.
It outputs six transparent sub-scores, a content-gap matrix, schema
recommendations, and a client-ready report. **The entire core is deterministic
and free** — no paid API, no key required; LLMs and embeddings are optional
enhancements that degrade gracefully.

## 2. The mental model: RAG, inverted

A normal RAG app asks *"given a question, retrieve context and generate an
answer."* AISO Copilot inverts the purpose: it asks *"if an answer engine ran its
retrieval over this page, would the page survive and be quotable?"*

| RAG stage | In a real answer engine | In AISO Copilot |
|---|---|---|
| Ingest | crawl the web | fetch/paste ONE page |
| Chunk | passage splitting | `src/retrieval/chunker.py` (section-aware) |
| Index | vector DB / inverted index | in-memory BM25 + TF-IDF + embeddings, per run |
| Query | the user's question | **generated** fan-out question set |
| Retrieve | top-k passages | per-question evidence + blended score |
| Generate | the answer | grounded "answer simulation" (template or LLM) |
| **Goal** | answer the user | **measure the page's fitness as a source** |

That inversion is the whole idea: we simulate the *retrieval and grounding* stage
to produce an auditable readiness score, not a chatbot.

## 3. Architecture & pipeline

```text
   Streamlit UI  ─┐                      ┌─ FastAPI (api/server.py)
                  ├──► src/services/analyzer.py · run_analysis() ◄──┤
   CLI  ──────────┘            (single shared entry point)
                                        │
   input → extract → entities → structure audit → fan-out → chunk →
   coverage → sourceability → schema → SCORES → [search console] →
   n8n blueprint → answer simulations → report (.md/.json)
```

Layers (all under `src/`, 45 modules):
- **crawler/** — fetch (graceful failure), extract HTML/MD/text → structured page
  object, JSON-LD parsing.
- **query/** — fan-out templates, bilingual intent classifier, EN↔TH glossary.
- **retrieval/** — chunker, BM25, TF-IDF, embeddings, hybrid coverage (each
  retriever has a pure-Python fallback).
- **audit/** — structure (24 checks), entities (13 categories), sourceability
  (15 checks), schema recommender, score combiner.
- **llm/** — provider abstraction (no_llm / openrouter / ollama); `complete()`
  returns `str | None` and **never raises**.
- **search_console/**, **automation/**, **reports/**, **services/**.

Design rule: **frontends are thin**; all logic lives behind `run_analysis()`.

## 4. The model — how scoring works

**Overall AI Search Readiness** = transparent weighted blend of six sub-scores:

```text
overall = 0.25·query_coverage + 0.20·structure + 0.20·sourceability
        + 0.15·entity_clarity + 0.10·schema + 0.10·technical_extractability
```

The heart is **query coverage**, a hybrid retrieval blend per question:

```text
score = 0.40·term_overlap + 0.35·tfidf_cosine + 0.25·bm25_saturated   (default)
classify: ≥0.55 Covered · ≥0.40 Partial · else Missing
```

with regime-specific blends (cross-lingual, embeddings) selected automatically.
No LLM touches any score — every number traces to an explainable rule
(see [SCORING_RUBRIC](SCORING_RUBRIC.md)). LLMs only *add* fan-out questions,
nicer answer simulations, and summary polish.

## 5. What we improved (before → after)

The project started as a solid deterministic MVP. The recent work (on branch
`experiment/pythainlp-tokenizer-fewshot`) hardened it for real, multilingual
pages and added measurable rigor:

| Area | Before | After |
|---|---|---|
| Thai tokenization | character trigrams (fuzzy) | PyThaiNLP `newmm` words + trigram fallback |
| Fan-out (LLM) | single model, zero-shot | **multi-agent** (3 free models), **few-shot**, merged & deduped |
| LLM default | no_llm | **OpenRouter** default (still safe with no key) |
| Embeddings | off by default | **on by default**, multilingual, cached |
| Cross-lingual EN↔TH | English Qs scored ~0 on Thai pages | glossary bridge + multilingual embeddings |
| Comparison Qs | could emit "SEO vs SEO" | distinct-baseline dedup |
| HTML extraction | mashed inline text ("DATA-LEDCREATIVE…") | `get_text(separator=" ")` + substring fallback |
| Evaluation | none | labeled eval harness + weight/threshold sweeps |
| Tests | 32 | **44** (added cross-lingual, multi-agent, LLM-fallback, e2e) |

**Measured cross-lingual gain** (21 labeled EN↔TH judgments):

| Config | Exact accuracy | Answerable recall |
|---|---|---|
| Original default | 43% | 64% |
| + overlap-weighted lexical | 57% | 79% |
| **+ multilingual embeddings + tuned blend (shipped)** | **67%** | **86%** |

## 6. Problems — solved, and still open

**Problems we faced and solved**
1. *Cross-lingual mismatch* — English questions vs Thai content scored ~0.
   Fixed with a deterministic EN↔TH glossary bridge + multilingual embeddings.
2. *Tokenization blind spots* — Thai has no spaces; layout text got mashed.
   Fixed with newmm segmentation and separator-aware extraction.
3. *Template bug* — "X vs X" comparisons. Fixed with distinct-baseline logic.
4. *"Is the tuning real or vibes?"* — built a labeled eval harness so weight and
   threshold choices are data-driven, not guessed (and recorded a *negative*
   threshold result rather than overfit).
5. *LLM fragility* — any provider error must never break the audit. Enforced by
   the `complete() → str | None` contract + per-model fallback, covered by tests.

**Problems we still face**
1. **Tiny eval set (n=21, subjective labels).** All tuning is directional. The
   single biggest credibility gap.
2. **Glossary coverage.** The EN↔TH bridge is domain-scoped; out-of-domain terms
   rely on embeddings or shared Latin tokens.
3. **Single-page scope.** No site authority, backlinks, or off-page brand signals
   — which real engines weigh heavily.
4. **No ground truth vs real engines.** We measure readiness, not actual
   citations/rankings (by design, but it caps how "real" the simulation is).
5. **Heavy optional dep.** Embeddings pull torch (~hundreds of MB) — kept out of
   core requirements so free-tier hosting still works.

**How we'd improve each** → see the roadmap (§9).

## 7. How we evaluate

Two complementary layers:

1. **Correctness & safety — `pytest` (44 tests, offline, no keys):** fan-out
   determinism, coverage classification bounds, scoring math, schema validity,
   LLM-failure fallback, multi-agent merge/dedup, full e2e demo. Tests force the
   deterministic path (`conftest` sets `AISO_USE_EMBEDDINGS=0`) so they're fast
   and reproducible anywhere.
2. **Quality — labeled eval harness (`evals/`):** a hand-labeled cross-lingual
   dataset (Covered/Partial/Missing judgments) plus `run_crosslingual_eval.py`,
   which sweeps blend weights and thresholds and reports **exact accuracy,
   ordinal MAE, answerable-recall, and worst-case (off-by-2) flips**. This is how
   every weight decision was made — and how we *declined* to change thresholds
   when the data showed no benefit.

```bash
pytest -q                                            # correctness
AISO_USE_EMBEDDINGS=1 python -m evals.run_crosslingual_eval   # quality sweep
```

## 8. "Is it good? Can it simulate a real search engine?"

**Honest answer: it faithfully simulates the *retrieval-and-grounding stage* of
an answer engine — not a full search engine.** Here's the split:

**What is genuinely faithful**
- Same RAG ingestion shape: parse → chunk → index → retrieve → ground.
- Query fan-out mirrors how assistants decompose a question into sub-questions.
- Hybrid lexical + semantic retrieval is the same family real systems use.
- Grounded answer simulation uses *only* retrieved evidence and flags missing
  evidence — i.e., it models "can this page support a citation?"

**What is deliberately NOT replicated**
- No live crawl, no web-scale index, no ranking algorithm, no personalization.
- Single-page scope; no off-page authority/backlinks/brand mentions.
- We never scrape or query real engines, and we predict **readiness, not
  outcomes** (no "you will be cited" claims).

**So how do we know it's "good"?** Four concrete signals:
1. **It separates good from bad pages** — the intentionally-flawed sample scores
   ~71–74 with the planted gaps (thin metrics, no case study) surfaced as the
   exact priority actions.
2. **Measured accuracy on labeled data** — 67% exact / 86% answerable-recall
   cross-lingual, and it correctly returns Missing for nonsense questions.
3. **Reproducibility** — deterministic core: same input → same scores, every run.
4. **Robustness** — 44 tests, graceful degradation when any optional layer
   (LLM, embeddings, a parser) is missing.

The credible claim in an interview is: *"It's a transparent, evaluated
**decision-support simulator** for answer-engine sourceability — not a ranking
predictor."* Overclaiming the latter is the trap; the honesty is a strength.

## 9. Roadmap

**Near-term (highest leverage first)**
1. **Grow the eval set** to 100+ labeled judgments across more domains/languages
   — turns "directional" into "benchmarked" and unlocks trustworthy tuning.
2. **Expand the EN↔TH glossary** + add a second language to prove generality.
3. **Confidence labels** on coverage rows (lexical-only vs embedding-backed).

**Mid-term**
4. **Multi-page / site mode** — audit a sitemap, add internal-link/topical-depth
   signals (a step toward authority).
5. **Before/after diffing** — re-audit a page after edits and show score deltas.
6. **Answer-simulation eval** — faithfulness/grounding metrics (does the
   simulated answer use only cited evidence?).

**Longer-term**
7. **Optional real-signal calibration** — let users paste their own AI-Overview /
   assistant citation observations to calibrate the readiness score against
   reality (still no scraping).
8. **Lightweight hosted embedding option** to bring semantics to free-tier deploys
   without bundling torch.

## 10. Interview script (presenting this project)

> Use this when presenting AISO Copilot in an interview (AI Engineer / GenAI /
> Martech). Lead with the inversion idea, then prove rigor with the eval harness.

**A. 30-second pitch**
> "AISO Copilot audits whether a web page is ready to be cited by AI answer
> engines. It treats the problem as RAG inverted — instead of answering a user, it
> simulates the engine's retrieval over the page and scores how quotable the page
> is. The core is fully deterministic and free; LLMs and embeddings are optional
> layers that degrade gracefully. I made every tuning decision with a labeled
> eval harness, not by guessing."

**B. 2-minute walkthrough**
> "Input is a URL or pasted page. I parse it into a structured object — headings,
> sections, FAQ, JSON-LD — then chunk it like a RAG ingest. I generate a
> 'query fan-out' — the sub-questions an assistant would explore — and score each
> against the page with a hybrid of BM25, TF-IDF, term-overlap, and multilingual
> embeddings, classifying Covered/Partial/Missing with evidence. That rolls up
> into six explainable sub-scores and a client report. The interesting
> engineering was making it work on real Thai pages with English questions, and
> proving the improvements with evaluation."

**C. Anticipated questions + strong answers**

- *"Is this just keyword matching?"*
  "No — it's a hybrid blend. Lexical signals (BM25/TF-IDF/overlap) catch exact
  entity and keyword bridges; multilingual embeddings catch paraphrase and
  cross-lingual meaning. I measured that combining both beats either alone:
  67% vs 57% exact on my labeled set."

- *"How did you handle Thai (or cross-lingual) content?"*
  "Three layers: PyThaiNLP word segmentation instead of naive trigrams; a
  deterministic EN↔TH glossary that expands the retrieval query and matches via
  concept groups; and a multilingual embedding model for semantic bridging —
  EN 'What is SEO?' vs TH 'SEO คือ…' embeds at 0.84 cosine. Coverage on a Thai
  page went from 5 to 32 with the deterministic bridge alone."

- *"How do you know your scoring is right?"*
  "I built an eval harness with hand-labeled Covered/Partial/Missing judgments
  and swept weights and thresholds, optimizing exact accuracy and answerable
  recall while watching worst-case flips. I even have a documented *negative*
  result — I tested cross-lingual thresholds, found the current ones already
  optimal, and chose not to change them rather than overfit 21 examples."

- *"What happens if the LLM/API fails?"*
  "Nothing breaks. The provider contract is `complete() returns str or None`,
  never raises. Missing key, stale model, rate limit, timeout — all caught, and
  the pipeline continues on deterministic templates. It's tested."

- *"What would you do with more time?"* — "Grow the eval set to 100+ judgments;
  it's the single biggest lever on credibility. Then site-level signals and
  before/after diffing."

- *"What's the biggest limitation?"* — "It predicts *readiness*, not actual
  citations, and it's single-page. I'm deliberate about not overclaiming — it's
  decision support, not a ranking predictor. Being honest about that is part of
  the design."

**D. What to demo live**
1. Sample Demo → Analyze (works offline, zero keys) → Overview scorecards.
2. Coverage Matrix → open a Missing question → show evidence + recommendation.
3. Query Fan-out → show multi-agent `openrouter:<model>` sources (if key set).
4. `python -m evals.run_crosslingual_eval` → show the measured tuning.

**E. If you are the interviewer (evaluating an intern on this codebase)**
Good probes: "Trace one number from the UI back to the rule that produced it."
· "Why are tests forced onto the deterministic path?" · "Where would a stale
OpenRouter slug break things, and why doesn't it?" · "What would you measure to
prove a weight change is real?" Strong candidates reach for the eval harness.

---

*Maintained alongside the codebase. Numbers in §5/§8 come from the labeled eval
in `evals/` and may shift as the dataset grows — re-run the harness to refresh.*
