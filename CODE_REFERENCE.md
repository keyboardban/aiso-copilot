# AISO Copilot — Code Reference

Per-module task and per-function description, **auto-generated from docstrings** by `scripts/gen_code_reference.py` (parsed with `ast`, no code executed). Re-run that script after code changes to refresh.

Covers 35 modules across `src/`, `api/`, and `app/`. For how the modules fit together see [ARCHITECTURE_DETAILED.md](ARCHITECTURE_DETAILED.md).

## Contents

- [`src`](#src)
- [`src/utils`](#srcutils)
- [`src/input`](#srcinput)
- [`src/crawler`](#srccrawler)
- [`src/query`](#srcquery)
- [`src/retrieval`](#srcretrieval)
- [`src/audit`](#srcaudit)
- [`src/search_console`](#srcsearch_console)
- [`src/llm`](#srcllm)
- [`src/automation`](#srcautomation)
- [`src/reports`](#srcreports)
- [`src/services`](#srcservices)
- [`api`](#api)
- [`app`](#app)


<a id="src"></a>
## `src`
### `src/config.py`

_Central configuration for AISO Copilot._

**Functions**

- **`get_env(name: str, default: str='') -> str`**
- **`ensure_output_dirs(base: Path=None) -> dict`** — Create output directories (idempotent) and return their paths.


<a id="srcutils"></a>
## `src/utils`

Shared low-level helpers (tokenization, text).

### `src/utils/text.py`

_Shared text utilities: tokenization, stopwords, sentence splitting._

**Functions**

- **`normalize_ws(text: str) -> str`** — Collapse whitespace runs into single spaces.
- **`contains_thai(text: str) -> bool`**
- **`tokenize(text: str, remove_stopwords: bool=False) -> list`** — Tokenize mixed Thai/English text.
- **`content_terms(text: str) -> set`** — Unique evidence-bearing terms of a query (stopwords removed).
- **`split_sentences(text: str) -> list`** — Light sentence splitter. Thai text without punctuation stays as one sentence per paragraph line — a documented limitation, fine for snippets.
- **`word_count(text: str) -> int`** — Word count that approximates Thai words as ~4 characters each.
- **`slugify(text: str, max_len: int=60) -> str`**
- **`truncate(text: str, max_chars: int=280) -> str`**


<a id="srcinput"></a>
## `src/input`

Input validation and sample/demo data loading.

### `src/input/sample_loader.py`

_Loads bundled sample data so the full demo works offline with no API keys._

**Functions**

- **`list_samples() -> list`** — Names of analyzable sample pages (markdown/html) in data/samples/.
- **`load_sample(name: str) -> dict`** — Return {name, content, source_type} for a bundled sample page.
- **`load_seed_questions() -> list`**
- **`load_competitors() -> dict`**
- **`sample_search_console_path() -> Path`**
- **`demo_defaults() -> dict`** — Everything the demo mode needs, pulled from bundled sample data.

### `src/input/validators.py`

_Input validation for URLs, pasted content, and seed questions._

**Functions**

- **`validate_url(url: str) -> dict`** — Return {ok, url, error}. Accepts http(s) URLs only; adds https:// if the user omitted a scheme.
- **`validate_pasted_content(content: str) -> dict`** — Return {ok, content, issues}. Truncates oversized pastes instead of failing.
- **`looks_like_html(content: str) -> bool`**
- **`parse_seed_questions(raw: str) -> list`** — One question per line; strips bullets/numbering, dedupes, caps length.
- **`clean_short_field(value: str, max_len: int=120) -> str`** — For topic / audience style inputs.


<a id="srccrawler"></a>
## `src/crawler`

Fetching and parsing pages into the structured page object.

### `src/crawler/extract_content.py`

_Turn raw HTML / Markdown / plain text into one structured page object._

**Functions**

- **`extract_content(raw: str, source_type: str='auto', url: str=None) -> dict`** — Main entry point. ``source_type``: html | markdown | text | auto.

### `src/crawler/fetch_page.py`

_Fetch a webpage over HTTP with friendly, structured failure modes._

**Functions**

- **`fetch_page(url: str) -> dict`** — Return {ok, url, final_url, status_code, html, error, suggestion}.

### `src/crawler/parse_schema.py`

_Extract structured data (JSON-LD, basic microdata) from HTML._

**Functions**

- **`parse_json_ld_from_soup(soup) -> dict`** — Return {json_ld: [objects], types: [str], parse_errors: [str]}.
- **`parse_microdata_types(soup) -> list`** — Very light microdata scan: collect schema.org itemtype values.


<a id="srcquery"></a>
## `src/query`

Query fan-out generation and bilingual intent/glossary logic.

### `src/query/bilingual.py`

_Bilingual (EN <-> TH) query-expansion bridge for cross-lingual retrieval._

**Functions**

- **`equivalents(term: str) -> list`** — Cross-language equivalents of a single content term (either direction).
- **`intent_cues(intent: str, want_thai: bool) -> list`** — Cue words for an intent in the requested language.
- **`bridge_terms(terms, intent: str, target_is_thai: bool) -> list`** — Flat list of expansion terms (in the target/page language) for a set of question content terms plus the intent's cue words. Deduplicated, order preserved. Used to enrich the BM25/TF-IDF retrieval query.

### `src/query/fanout_generator.py`

_Query fan-out generation: expand a topic into the question set an AI-assisted search system would likely explore._

**Functions**

- **`generate_fanout(topic: str, audience: str='', seeds: list=None, entities: dict=None, llm=None, agents: list=None, max_questions: int=MAX_FANOUT_QUESTIONS) -> dict`** — Return {"seed_questions", "fanout_questions", "llm_used", "llm_note", "agents_used"}.

### `src/query/templates.py`

_Deterministic question templates and intent classification for query fan-out._

**Functions**

- **`comparison_alts(topic: str, limit: int=2) -> list`** — Return up to ``limit`` comparison baselines distinct from ``topic``.
- **`classify_intent(question: str) -> str`**


<a id="srcretrieval"></a>
## `src/retrieval`

Chunking and the hybrid coverage retrieval engine.

### `src/retrieval/bm25_retriever.py`

_BM25 retrieval over page chunks._

**class `_PurePythonBM25`** — Minimal Okapi BM25 (k1=1.5, b=0.75) matching rank_bm25 semantics.
- **`__init__(self, corpus_tokens: list, k1: float=1.5, b: float=0.75)`**
- **`get_scores(self, query_tokens: list) -> list`**

**class `BM25Retriever`**
- **`__init__(self, chunks: list)`**
- **`score_all(self, query: str) -> list`** — Raw BM25 score for every chunk (parallel to ``chunks``).
- **`top_k(self, query: str, k: int=5) -> list`**

### `src/retrieval/chunker.py`

_Split a structured page into retrievable chunks._

**Functions**

- **`build_chunks(page: dict) -> list`** — Return [{"id", "section", "text", "word_count"}, ...].

### `src/retrieval/embedding_retriever.py`

_Local embedding retrieval (sentence-transformers)._

**Functions**

- **`embeddings_backend() -> str`** — Best-effort name of the active embedding model, or '' if unavailable.

**class `EmbeddingRetriever`**
- **`__init__(self, chunks: list)`**
- **`score_all(self, query: str) -> list`** — Cosine similarity (0..1) for every chunk; [] when unavailable.

### `src/retrieval/hybrid_coverage.py`

_Retrieval-based content coverage: can this page answer each fan-out question?_

**Functions**

- **`evaluate_coverage(chunks: list, questions: list, llm=None) -> dict`** — Return {"coverage_matrix": [...], "coverage_score": int, "method": str}.

### `src/retrieval/tfidf_retriever.py`

_TF-IDF cosine similarity retrieval over page chunks._

**class `_PurePythonTfidf`**
- **`__init__(self, corpus_tokens: list)`**
- **`similarities(self, query_tokens: list) -> list`**

**class `TfidfRetriever`**
- **`__init__(self, chunks: list)`**
- **`score_all(self, query: str) -> list`** — Cosine similarity (0..1) for every chunk (parallel to ``chunks``).
- **`top_k(self, query: str, k: int=5) -> list`**


<a id="srcaudit"></a>
## `src/audit`

Rule-based audits and the score combiner.

### `src/audit/entity_extractor.py`

_Deterministic entity and topic extraction._

**Functions**

- **`extract_entities(page: dict, target_topic: str='', target_audience: str='') -> dict`** — Return the Feature-4 entity object with clarity score and gaps.

### `src/audit/schema_recommender.py`

_Schema.org recommendation with a JSON-LD preview._

**Functions**

- **`recommend_schema(page: dict, entity_result: dict) -> dict`** — Return {recommended_schema_types, json_ld_preview, warnings, schema_score, existing_types, missing_types, notes}.

### `src/audit/scoring.py`

_Combine sub-scores into the overall AI Search Readiness score and derive priority actions. Weights live in config.READINESS_WEIGHTS; the full formula is documented in SCORING_RUBRIC.md._

**Functions**

- **`compute_scores(structure_result: dict, entity_result: dict, coverage_result: dict, sourceability_result: dict, schema_result: dict, technical: dict) -> dict`** — Return {"overall_ai_search_readiness", "subscores", "weights", "priority_actions"}.
- **`build_priority_actions(subscores: dict, structure_result: dict, entity_result: dict, coverage_result: dict, sourceability_result: dict, schema_result: dict, technical: dict) -> list`** — Actionable next steps, ordered by impact (weakest weighted areas first).

### `src/audit/sourceability.py`

_Sourceability / citation-readiness scoring._

**Functions**

- **`assess_sourceability(page: dict, entity_result: dict) -> dict`** — Return {sourceability_score, strong_evidence, missing_evidence, recommendations, checks}.

### `src/audit/structure_audit.py`

_Rule-based structure audit for AI Search readiness._

**Functions**

- **`audit_structure(page: dict, entity_result: dict) -> dict`** — Return {structure_score, strengths, weaknesses, recommendations, checks}.


<a id="srcsearch_console"></a>
## `src/search_console`

Search Console CSV loading and opportunity scoring.

### `src/search_console/csv_loader.py`

_Load and normalize a Google Search Console performance CSV export._

**Functions**

- **`load_search_console_csv(source) -> dict`** — Accepts a path, a file-like object (Streamlit upload), or a DataFrame.

### `src/search_console/opportunity_scoring.py`

_Turn normalized Search Console rows into AI-Search content opportunities._

**Functions**

- **`find_opportunities(df) -> dict`** — Return {"opportunities": [...], "summary": {...}} from a normalized Search Console DataFrame (see csv_loader).


<a id="srcllm"></a>
## `src/llm`

Optional LLM provider abstraction (no_llm / openrouter / ollama).

### `src/llm/no_llm_fallback.py`

_The default 'provider': no LLM at all._

**class `NoLLMProvider`**
- **`available(self) -> bool`**
- **`complete(self, prompt: str, system: str=None, max_tokens: int=700, temperature: float=0.4)`**

### `src/llm/ollama_provider.py`

_Optional local Ollama provider._

**class `OllamaProvider`**
- **`__init__(self, base_url: str, model: str='')`**
- **`available(self) -> bool`**
- **`complete(self, prompt: str, system: str=None, max_tokens: int=700, temperature: float=0.4)`**

### `src/llm/openrouter_provider.py`

_Optional OpenRouter provider (chat-completions over plain HTTP)._

**class `OpenRouterProvider`**
- **`__init__(self, api_key: str, model: str)`**
- **`available(self) -> bool`**
- **`complete(self, prompt: str, system: str=None, max_tokens: int=700, temperature: float=0.4)`**

### `src/llm/prompt_builder.py`

_Prompts for the optional LLM enhancement layer._

**Functions**

- **`build_fanout_prompt(topic: str, audience: str, seeds: list=None, n_shots: int=2) -> str`** — Few-shot fan-out prompt.
- **`build_answer_prompt(question: str, evidence: list) -> str`**
- **`build_polish_prompt(executive_summary: str) -> str`**
- **`parse_question_lines(text: str) -> list`** — Parse LLM output into clean question strings.

### `src/llm/provider_base.py`

_LLM provider abstraction._

**Functions**

- **`provider_label(provider) -> str`** — Readable source tag for a provider, e.g. 'openrouter:llama-3.3-70b'.
- **`build_openrouter_agents(api_key: str=None, models=None) -> list`** — Build one OpenRouterProvider per model slug for multi-agent fan-out.
- **`get_provider(mode: str, api_key: str=None, model: str=None, base_url: str=None, ollama_model: str=None) -> tuple`** — Resolve (provider, status_message) for a requested mode.

**class `LLMProvider`**
- **`available(self) -> bool`** — Cheap readiness check (config present / server reachable).
- **`complete(self, prompt: str, system: str=None, max_tokens: int=700, temperature: float=0.4)`** — Return generated text, or None on ANY problem (never raises).


<a id="srcautomation"></a>
## `src/automation`

n8n workflow blueprint generation.

### `src/automation/n8n_blueprint_generator.py`

_Generate an n8n automation blueprint (markdown + JSON files)._

**Functions**

- **`generate_n8n_blueprint(api_url: str='http://localhost:8000/analyze', project: str='AISO Copilot') -> dict`**
- **`blueprint_markdown(blueprint: dict) -> str`**
- **`write_blueprint_files(blueprint: dict, workflows_dir) -> list`**


<a id="srcreports"></a>
## `src/reports`

Markdown report and JSON export.

### `src/reports/json_exporter.py`

_JSON export for the full audit result._

**Functions**

- **`to_json_string(result: dict) -> str`**
- **`export_json(result: dict, path) -> str`**

### `src/reports/markdown_report.py`

_Client-style markdown audit report._

**Functions**

- **`build_executive_summary(result: dict) -> str`** — Deterministic executive summary template (LLM may polish it later).
- **`build_markdown_report(result: dict) -> str`**


<a id="srcservices"></a>
## `src/services`

Pipeline orchestration, metrics, run storage.

### `src/services/analyzer.py`

_AISO Copilot core analyzer — the single entry point used by both the Streamlit UI and the FastAPI backend._

**Functions**

- **`run_analysis(source_type: str, url: str=None, raw_content: str=None, sample_name: str=None, target_topic: str='', target_audience: str='', seed_questions=None, llm_mode: str=MODE_NO_LLM, openrouter_api_key: str=None, openrouter_model: str=None, ollama_base_url: str=None, ollama_model: str=None, search_console_source=None, write_files: bool=True, output_dir=None) -> dict`** — Run the full audit. ``source_type``: url | html | markdown | text | sample.

### `src/services/metrics.py`

_Basic readability metrics for extracted page text._

**Functions**

- **`text_metrics(text: str) -> dict`** — Word/sentence stats plus Flesch reading ease (English text only).

### `src/services/session_store.py`

_Persist analysis runs as local JSON files (free local storage, no database)._

**Functions**

- **`save_run(result: dict, runs_dir=None) -> str`**
- **`list_runs(runs_dir=None) -> list`**
- **`load_run(path) -> dict`**


<a id="api"></a>
## `api`

Optional FastAPI backend.

### `api/server.py`

_Optional FastAPI backend for AISO Copilot._

**Functions**

- **`health()`**
- **`analyze(request: AnalyzeRequest)`**
- **`fanout(request: FanoutRequest)`**
- **`coverage(request: CoverageRequest)`**
- **`schema_recommend(request: SchemaRequest)`**
- **`report_generate(request: ReportRequest)`**

**class `AnalyzeRequest`**

**class `FanoutRequest`**

**class `CoverageRequest`**

**class `SchemaRequest`**

**class `ReportRequest`**


<a id="app"></a>
## `app`

Streamlit dashboard.

### `app/streamlit_app.py`

_AISO Copilot — Streamlit dashboard._

**Functions**

- **`band_color(score: float) -> str`**
- **`gauge_chart(value: int, title: str)`**
- **`subscore_chart(subscores: dict, weights: dict)`**
- **`coverage_distribution_chart(matrix: list)`**
- **`hbar_chart(series: pd.Series, color=None, height: int=280, color_map: dict=None)`**
- **`entity_weight_chart(score_breakdown: dict, full_weights: dict)`** — Diverging bar chart: earned categories extend right (green), missed categories extend left (red) from a zero baseline. Bar length = how many clarity points the category is worth (all-or-nothing per category).
- **`sc_scatter_chart(df: pd.DataFrame)`**
- **`hero_header()`** — Branded page header: oversized title with a terracotta accent.
- **`section(title: str, description: str=None)`** — Stand-out section header: terracotta left rule + heavier type.
- **`style_status_table(df: pd.DataFrame, status_col: str)`**
- **`render_sidebar() -> dict`**
- **`execute_analysis(params: dict)`**
- **`tab_overview(result: dict)`**
- **`tab_structure(result: dict)`**
- **`tab_fanout(result: dict)`**
- **`tab_coverage(result: dict)`**
- **`tab_sourceability(result: dict)`**
- **`tab_entities(result: dict)`**
- **`tab_schema(result: dict)`**
- **`tab_search_console(result: dict)`**
- **`tab_n8n(result: dict)`**
- **`tab_report(result: dict)`**
- **`tab_raw_json(result: dict)`**
- **`main()`**
