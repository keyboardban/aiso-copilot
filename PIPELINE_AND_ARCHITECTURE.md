# Pipeline & Architecture

## High-level architecture

```text
                       ┌─────────────────────────────────────────────┐
                       │            FRONTENDS (thin layers)          │
                       │  Streamlit dashboard      FastAPI backend   │
                       │  app/streamlit_app.py     api/server.py     │
                       └───────────────┬─────────────────────────────┘
                                       │ one shared entry point
                                       ▼
                        src/services/analyzer.py  · run_analysis()
                                       │
        ┌──────────────┬───────────────┼────────────────┬──────────────┐
        ▼              ▼               ▼                ▼              ▼
   INPUT LAYER    EXTRACTION       AUDIT LAYER      RETRIEVAL      OPTIONAL LLM
   validators     extract_content  structure_audit  chunker        provider_base
   sample_loader  parse_schema     entity_extractor bm25/tfidf     openrouter
   fetch_page     (bs4/trafila-    sourceability    (+embeddings)  ollama
                  tura/markdown)   schema_recommend hybrid_coverage no_llm_fallback
                                   scoring
        │              │               │                │              │
        └──────────────┴───────────────┼────────────────┴──────────────┘
                                       ▼
                  OUTPUTS: markdown_report · json_exporter ·
                  n8n_blueprint_generator · session_store
                  (+ search_console: csv_loader · opportunity_scoring)
```

Design rule: **the core is a plain modular Python pipeline** (no agent framework, no
LlamaIndex/LangChain — they were considered and skipped as unnecessary for a
single-page, deterministic audit). The Streamlit and FastAPI layers contain no
analysis logic; both call the same `run_analysis()`.

## Data flow (one audit)

```text
input (url | paste | sample)
  → validate (src/input/validators.py)
  → fetch if URL (src/crawler/fetch_page.py — graceful failure → suggest paste mode)
  → extract_content() → structured PAGE object (title, meta, headings, sections,
      links, FAQ blocks, JSON-LD, word count, technical extractability)
  → extract_entities(PAGE)                        # rule-based, deterministic
  → audit_structure(PAGE, entities)               # 24 weighted checks
  → generate_fanout(topic, audience, seeds, entities, llm?)   # templates first
  → build_chunks(PAGE)                            # section-based passages
  → evaluate_coverage(chunks, questions)          # BM25 + TF-IDF + term overlap
  → assess_sourceability(PAGE, entities)          # 15 evidence checks
  → recommend_schema(PAGE, entities)              # content-backed JSON-LD preview
  → compute_scores(...)                           # weighted overall + priority actions
  → [optional] search console CSV → opportunities
  → generate_n8n_blueprint()                      # files only, no live connection
  → simulate_answers(matrix, llm?)                # grounded, template fallback
  → build report (markdown + JSON) → outputs/
```

## Module responsibilities

| Module | Responsibility | Key contract |
|---|---|---|
| `src/config.py` | All paths, thresholds, weights, env loading | constants only — keeps scoring transparent |
| `src/utils/text.py` | Tokenization (Thai trigram-aware), stopwords, sentences | `tokenize()` is shared by ALL retrieval so scores are consistent |
| `src/input/validators.py` | URL/paste/seed validation | returns structured `{ok, …}`, never raises on user input |
| `src/input/sample_loader.py` | Offline demo data | `demo_defaults()` powers the one-click demo |
| `src/crawler/fetch_page.py` | Best-effort HTTP fetch | every failure → `{ok: False, error, suggestion}` |
| `src/crawler/extract_content.py` | HTML/Markdown/text → structured page object | the page dict every module consumes (schema below) |
| `src/crawler/parse_schema.py` | JSON-LD + light microdata extraction | tolerant parsing, errors reported not raised |
| `src/query/templates.py` | 20 core templates + bilingual intent rules | first-match-wins rule cascade, 11 intents |
| `src/query/fanout_generator.py` | Seeds + templates + entity extras (+ LLM extras) | LLM additions are additive only |
| `src/retrieval/chunker.py` | Section-based passage chunks | heading prepended to each chunk |
| `src/retrieval/bm25_retriever.py` | BM25 (rank-bm25 → pure-Python fallback) | `score_all(query)` parallel to chunks |
| `src/retrieval/tfidf_retriever.py` | TF-IDF cosine (sklearn → pure-Python fallback) | same interface |
| `src/retrieval/embedding_retriever.py` | OPT-IN local embeddings | `available=False` unless explicitly enabled |
| `src/retrieval/hybrid_coverage.py` | Blend signals → Covered/Partial/Missing + evidence | no LLM, thresholds in config |
| `src/audit/*` | Structure / entities / sourceability / schema / scoring | each returns score + explainable check list |
| `src/search_console/*` | CSV load/normalize + opportunity rules | one primary opportunity per row, precedence-ordered |
| `src/llm/*` | Provider abstraction | `complete() → str or None`, NEVER raises |
| `src/automation/n8n_blueprint_generator.py` | Blueprint markdown + JSON | documentation artifact only |
| `src/reports/*` | Markdown report + JSON export | report renders fully in no-LLM mode |
| `src/services/analyzer.py` | Orchestration + answer simulations + file writing | the only function frontends call |
| `src/services/metrics.py` / `session_store.py` | Readability stats / local run history | local JSON storage, no DB |

## The page object (extraction contract)

```json
{
  "source_type": "html | markdown | text",
  "url": null,
  "title": "...", "meta_description": "...",
  "headings": {"h1": [], "h2": [], "h3": []},
  "body_text": "...",
  "sections": [{"heading": "...", "level": 2, "content": "...", "word_count": 0}],
  "links": {"internal": [{"text": "...", "href": "..."}], "external": []},
  "faq_blocks": [{"question": "...", "answer": "..."}],
  "json_ld": [], "json_ld_types": [], "json_ld_errors": [], "microdata_types": [],
  "word_count": 0,
  "technical_extractability": {"status": "ok|warning|poor", "score": 0, "issues": []},
  "extractor": "beautifulsoup | trafilatura+beautifulsoup | markdown | plaintext"
}
```

The final result object follows the spec §10 schema with documented additions:
`ok` (graceful-failure flag), `generated_at`, `seed_questions`, `coverage_method`,
`search_console_summary`, `executive_summary`, `report_markdown` (in-memory only —
not written into `audit_result.json`), and `input.llm_status`.

## Retrieval & coverage design

1. **Chunking** — sections become passages (~110 words target, 170 max), the heading
   prepended to each chunk because question-shaped headings carry retrieval signal.
   Title + meta description form one extra "Page metadata" chunk.
2. **Signals per question** (each 0..1):
   - `term_overlap`: fraction of the question's content terms present in the chunk
     (absolute evidence — prevents "similar topic" from passing as "answered")
   - `tfidf`: cosine similarity (sklearn or pure-Python twin)
   - `bm25`: saturated raw score `s/(s+6)` (rank-bm25 or pure-Python Okapi twin)
   - optional `embeddings`: cosine from local sentence-transformers (opt-in)
3. **Blend** — `0.40·overlap + 0.35·tfidf + 0.25·bm25` (re-weighted to
   .30/.25/.20/.25 when embeddings are enabled).
4. **Classify** — Covered ≥ 0.55, Partial ≥ 0.40, else Missing. The Partial floor sits
   *above* the ~0.30–0.40 band a question reaches by merely sharing the page's topic
   phrase — matching the topic is not the same as answering the question.

**Thai handling:** Thai has no word spaces. Thai runs are tokenized into character
trigrams (shared `tokenize()`), with a stop-particle strip before trigramming. This is
a deliberate free approximation that lets Thai seed questions retrieve Thai passages
without a segmentation dependency.

## Fallback strategy (no-paid-API design)

| Layer | Primary | Fallback | Trigger |
|---|---|---|---|
| LLM | OpenRouter (user's free slug) / Ollama | rule-based templates | missing key/model, any HTTP/quota/auth error, empty completion |
| BM25 | rank-bm25 | built-in pure-Python Okapi | package not installed |
| TF-IDF | scikit-learn | built-in pure-Python TF-IDF | package not installed / empty vocabulary |
| Body text (HTML) | trafilatura | BeautifulSoup heuristics | package missing or low-yield extraction |
| HTML parser | lxml | html.parser | lxml missing |
| Embeddings | sentence-transformers | simply omitted from blend | not installed or `AISO_USE_EMBEDDINGS≠1` |
| URL input | requests fetch | clear error + paste-mode suggestion | any network/HTTP problem |
| Search Console | CSV upload | feature skipped with notice | no CSV provided / unreadable CSV |

The LLM contract is the load-bearing piece: `LLMProvider.complete()` returns
`str | None` and **never raises**. Call sites treat `None` as "use the template path",
which makes no-LLM mode a first-class path rather than an error state.

## Frontends

- **Streamlit** (`app/streamlit_app.py`) — sidebar (input mode, topic/audience/seeds,
  CSV upload, LLM mode with conditional OpenRouter/Ollama fields) + 11 tabs. Results
  live in `st.session_state`; downloads are served from memory so the app also works
  on ephemeral filesystems (Streamlit Community Cloud).
- **FastAPI** (`api/server.py`) — `GET /health`, `POST /analyze`, `/fanout`,
  `/coverage`, `/schema/recommend`, `/report/generate`. Pydantic request models;
  `write_files=False` by default so API calls don't touch disk unless asked. This is
  the endpoint the generated n8n blueprint points at.

## Deviations from the original build spec (documented intentionally)

1. **Repo root = project root** — the working directory already *is* `AISO-copilot/`,
   so no nested `aiso-copilot/` folder was created.
2. **`src/utils/text.py` added** — one shared Thai-aware tokenizer beats three private
   copies in the retrievers.
3. **Answer simulation lives in `services/analyzer.py`** — it consumes the coverage
   matrix and the LLM handle that already live there; a separate module would only
   re-plumb arguments.
4. **`"seed"` added to the fan-out `source` enum** (spec listed template/openrouter/
   ollama) so seed questions flow through coverage scoring with provenance intact.
5. **Pure-Python retrieval fallbacks** — beyond spec; makes the demo run even on a
   minimal Python install and keeps tests green anywhere.
6. **Entity extraction is deterministic-only** — the spec allowed optional LLM
   refinement; it was skipped because entities feed core scoring, which must stay
   reproducible. LLMs touch only fan-out extras, answer simulations, and summary polish.
7. **Tests: 6 files instead of 4** — the four required plus `test_llm_fallback.py` and
   `test_analyzer_e2e.py` (the spec's MVP criteria demand these behaviors be tested;
   separate files keep them readable).
