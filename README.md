# 🔎 AISO Copilot — Free AI Search Visibility Auditor

> A zero-cost AI Search audit platform for query fan-out coverage, sourceability scoring,
> content gap detection, schema recommendations, and client-ready audit reports.

AISO Copilot audits whether a webpage is ready to be **understood, retrieved, cited,
summarized, and recommended** by AI-assisted search systems and answer engines
(GEO / Answer Engine Optimization). It is built like a practical agency tool, not a
generic SEO dashboard: it generates the question set an AI assistant would explore,
checks which questions your content can actually answer **with evidence**, scores
citation readiness, and exports a client-style audit report.

```text
Core analysis = local + free + deterministic
Optional LLM  = OpenRouter free model or local Ollama
Fallback      = rule-based templates
```

**The default mode requires no API key, no billing, no internet, and no LLM.**

---

## Why this exists

Search is shifting from ranked links to generated answers. An AI assistant answering
"What is X?" fans the question out into sub-questions, retrieves candidate passages,
and composes an answer from sources it can confidently quote. Pages win that selection
by being **quotable**: clear definitions, direct answers, consistent entities, explicit
evidence, and structured data that matches the visible text.

Classic SEO tools don't measure any of that. AISO Copilot does — with transparent,
deterministic scoring you can explain to a client line by line.

## What it does

| Feature | What you get |
|---|---|
| 🧩 **Query fan-out generator** | 20+ template questions (+ seeds, + entity-aware extras), classified into 11 intents — bilingual EN/TH rules, no LLM needed |
| 🗺 **Coverage matrix** | Per-question Covered / Partial / Missing via hybrid BM25 + TF-IDF + term-overlap retrieval, with evidence snippets and gap recommendations |
| 🧱 **Structure audit** | 24 weighted checks: titles, direct-answer blocks, FAQ, process steps, trust signals… |
| 🏷 **Entity clarity** | Brand, services, audiences, problems, proof points — extracted by rules + JSON-LD |
| 📌 **Sourceability score** | 15-point citation-readiness checklist: definitions, steps, numbers, proof, freshness |
| 🧬 **Schema recommendations** | Recommended types + copy-paste JSON-LD preview built *only* from visible content |
| 📈 **Search Console opportunities** | CSV upload → prioritized AI-search opportunities (no API, no OAuth) |
| 🤖 **Answer simulations** | "How would an answer engine respond using only this page?" — grounded, template-based |
| ⚙️ **n8n blueprint** | Generated automation workflow (markdown + JSON) — documentation, not a live connection |
| 📄 **Client-ready report** | Markdown + JSON export with executive summary, gap matrix, and action plan |

## Screenshots-in-words

The Streamlit dashboard has 11 tabs: **Overview** (readiness scorecards + radar +
priority actions), **Structure Audit**, **Query Fan-out**, **Coverage Matrix** (with
per-question evidence and simulated AI answers), **Sourceability**, **Entities**,
**Schema**, **Search Console**, **n8n Blueprint**, **Report** (preview + 4 download
buttons), and **Raw JSON**.

---

## Quickstart (100% free)

```bash
# 1. clone / open the project, then:
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. run the dashboard
streamlit run app/streamlit_app.py
```

In the sidebar keep **Sample Demo** selected and click **🚀 Analyze AI Search
Readiness**. The demo audits a bundled (intentionally imperfect) agency service page,
including Thai seed questions and a sample Search Console CSV — fully offline.

### CLI demo

```bash
python -m src.services.analyzer --with-search-console
# writes outputs/reports/AI_SEARCH_AUDIT_REPORT.md, audit_result.json,
# and outputs/workflows/n8n_workflow_blueprint.{md,json}
```

### Optional API backend

```bash
uvicorn api.server:app --reload --port 8000
# GET /health · POST /analyze /fanout /coverage /schema/recommend /report/generate
```

### Tests

```bash
pytest -q          # 32 tests, all offline, no keys required
```

### Deploy for free (Streamlit Community Cloud)

The app is hosting-ready: no database, no background workers, and all downloads are
served from memory (ephemeral filesystems are fine).

1. Push this repo to GitHub (public).
2. At [share.streamlit.io](https://share.streamlit.io), choose **New app**, select the
   repo, and set the entry point to `app/streamlit_app.py`.
3. That's it — dependencies install from `requirements.txt` automatically.

Never commit `.env`. If you want the optional OpenRouter mode on a hosted instance,
set `OPENROUTER_API_KEY` in the app's **Secrets** settings instead — or simply leave
the deployment in the default no-LLM mode, which needs no secrets at all.
(Alternative free hosts: Hugging Face Spaces with the Streamlit SDK, or Render's free
tier — which can also serve the FastAPI backend via `uvicorn api.server:app`.)

---

## LLM modes (all optional)

| Mode | Cost | What it adds | What happens if it fails |
|---|---|---|---|
| **No LLM** (default) | $0, no key | Nothing — full audit runs deterministically | n/a — this *is* the fallback |
| **OpenRouter** | $0 if **you** pick a free model slug | Extra fan-out questions, nicer answer simulations, polished executive summary | Any auth/quota/provider error → silent fallback to templates |
| **Ollama** | $0, local | Same as above, fully local | Server unreachable → silent fallback |

Hard rules baked into the code:

- OpenRouter is **never called by default** and **no model slug is hardcoded** — you
  supply both the key and the model (pick a `:free` slug on openrouter.ai/models).
- LLMs are used **only** for additive polish. Scoring, extraction, retrieval, coverage,
  and schema logic are 100% deterministic and LLM-free.
- A missing key, missing model, or any API error can never crash the app — providers
  return `None` and the template path takes over (see `tests/test_llm_fallback.py`).

Configuration via `.env` (copy `.env.example`) or directly in the sidebar.

## Free-first design

No paid APIs, SaaS, crawlers, databases, or hosting anywhere in the core:

- **Fetching/parsing:** requests + BeautifulSoup + trafilatura (all free)
- **Retrieval:** rank-bm25 + scikit-learn TF-IDF — with **pure-Python fallbacks built
  in**, so the analyzer even survives a partial install
- **Thai support:** character-trigram matching (no segmentation service needed)
- **Storage:** local JSON files (`outputs/`) — no database
- **Optional extras** (`requirements-local.txt`): local sentence-transformers
  embeddings (`AISO_USE_EMBEDDINGS=1`), extruct, readability-lxml — still free
- **Search Console:** CSV upload only — no API, no OAuth, no billing surface at all

## Sample data

| File | Purpose |
|---|---|
| `data/samples/sample_page.md` / `.html` | Agency service page, intentionally imperfect: good definitions, weak metrics, thin FAQ, no case studies, partial schema — so the auditor has real gaps to find |
| `data/samples/seed_questions.txt` | 8 Thai-language seed questions |
| `data/samples/search_console_sample.csv` | 30 realistic GSC rows (EN + TH queries) |
| `data/samples/competitors_sample.json` | Brand/market/audience context for the demo |

## Scores at a glance

**Overall AI Search Readiness** = weighted blend of six sub-scores
(structure 20% · entity clarity 15% · query coverage 25% · sourceability 20% ·
schema 10% · technical extractability 10%). Every check, weight, threshold, and
formula is documented in [SCORING_RUBRIC.md](SCORING_RUBRIC.md).

## Project structure

```text
app/streamlit_app.py      # dashboard (11 tabs)
api/server.py             # optional FastAPI backend
src/
  crawler/                # fetch, extract, JSON-LD parsing
  audit/                  # structure, entities, sourceability, schema, scoring
  query/                  # fan-out templates + generator
  retrieval/              # chunker, BM25, TF-IDF, embeddings, hybrid coverage
  search_console/         # CSV loader + opportunity rules
  llm/                    # provider abstraction: no_llm / openrouter / ollama
  automation/             # n8n blueprint generator
  reports/                # markdown report + JSON export
  services/               # analyzer orchestrator, metrics, session store
data/samples/             # offline demo data
outputs/                  # generated reports / workflows / runs (gitignored)
tests/                    # 32 offline tests
```

Architecture details: [PIPELINE_AND_ARCHITECTURE.md](PIPELINE_AND_ARCHITECTURE.md).

## Honest limitations

This tool estimates **readiness**, nothing more. It does not measure or predict actual
AI Overview inclusion, ChatGPT/Perplexity citations, or rankings; it never scrapes
search engines; single-page scope means site authority and off-page signals are out of
scope; Thai matching is an n-gram approximation; URL mode cannot render JavaScript.
Full discussion: [MODEL_AND_LIMITATIONS.md](MODEL_AND_LIMITATIONS.md).

---

*Built as a portfolio project for AI Engineer / Generative AI / AI Search Optimization
/ Martech roles — demonstrating retrieval engineering, explainable scoring, graceful
LLM degradation, and free-first product design.*
