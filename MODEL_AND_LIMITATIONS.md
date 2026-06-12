# Models & Limitations

## No paid model — ever

AISO Copilot's core pipeline (extraction, entity analysis, structure audit, query
fan-out, retrieval coverage, sourceability, schema recommendation, scoring, reports)
is **100% deterministic Python**. It runs with:

- no API key
- no LLM
- no billing account
- no internet connection (in Sample Demo / paste mode)

## The three LLM modes

### 1. `no_llm` (default)

The default and the reference behavior. Fan-out comes from 20+ bilingual templates,
answer simulations are grounded text assembled from retrieved evidence, and the report
uses a deterministic executive-summary template. Nothing degrades: this mode produces
the complete audit, report, and exports.

### 2. `openrouter` (optional)

- **You** supply both `OPENROUTER_API_KEY` and a model slug — the tool hardcodes no
  model and never selects one for you. Choose a free-tier slug (they end in `:free`
  on openrouter.ai/models); the user is responsible for picking a free model.
- Called only when explicitly selected, and only for: extra fan-out questions,
  nicer answer simulations (max 4 per run), and executive-summary polish.
- **Never** used for: scoring, extraction, retrieval, coverage classification, schema
  validation, or any required functionality.
- Failure handling: missing key/slug → the provider is never constructed; quota,
  rate-limit, payment, auth, provider, timeout, and parse errors are all caught and
  return `None` → template path continues. The UI reports which mode actually ran.

### 3. `ollama` (optional, local)

Same enhancement scope as OpenRouter, fully local. If the server at `OLLAMA_BASE_URL`
is unreachable or has no models, the app silently uses no-LLM mode. If no model name
is configured, the first locally installed model is used.

## Local retrieval approach

- BM25 (rank-bm25, with a built-in pure-Python Okapi twin) + TF-IDF cosine
  (scikit-learn, with a pure-Python twin) + content-term overlap, blended and
  thresholded (see SCORING_RUBRIC.md).
- Optional, opt-in local embeddings via sentence-transformers
  (`requirements-local.txt` + `AISO_USE_EMBEDDINGS=1`). The model downloads once,
  runs locally, and costs nothing. When absent, the blend simply runs without it.
- Thai is handled with character trigrams — a free approximation of word
  segmentation that works well for matching, not for linguistics.

## What the tool CAN infer

- Whether a page's content can answer a realistic AI-search question set, with the
  supporting evidence passages shown
- Whether the page contains quotable evidence (definitions, steps, numbers, proof)
  that generated answers need
- Whether brand/service/audience entities are stated clearly enough to disambiguate
- Which schema.org types the visible content can legitimately support
- How cleanly machines can extract the content (headings, text ratio, noindex…)
- Which Search Console queries look like AI-answer opportunities (from your CSV)

## What the tool CANNOT infer

- Whether Google AI Overviews, ChatGPT, Perplexity, or any assistant **actually**
  cites or recommends the page — no such claim is made anywhere
- Rankings, traffic, or click outcomes
- Site-level authority, backlinks, off-page brand mentions (single-page scope)
- Content **truthfulness** — it verifies evidence *presence*, not factual accuracy
- JavaScript-rendered content in URL mode (paste the rendered HTML instead)

## Hard scope boundaries (by design)

- **No search engine scraping.** The tool never queries or scrapes Google, Bing,
  ChatGPT, Perplexity, or any answer engine.
- **No ranking/citation guarantees.** All copy says "estimated readiness" — treat
  every number as decision support for a human reviewer.
- **No spam generation.** The tool audits and recommends; it does not mass-generate
  content, and the n8n blueprint deliberately includes a human-review step and
  explicitly warns against bulk-content automation.
- **No paid services.** Requirements contain no paid SDKs; Search Console analysis is
  CSV-only (no API/OAuth); storage is local JSON.

## Known approximations

| Area | Approximation | Impact |
|---|---|---|
| Thai tokenization | character trigrams, stop-particle substring removal | good matching, no real segmentation |
| Word counts | Thai ≈ 4 chars/word | counts are estimates for mixed text |
| Sentence splitting | punctuation/newline based | Thai paragraphs may stay one "sentence" |
| Readability | Flesch on the English portion only | skipped/flagged for Thai-dominant text |
| FAQ detection | question-headings + FAQ containers + Q:/A: patterns | unconventional FAQ markup may be missed |
| Brand detection | JSON-LD → title suffix → domain | pages with none of these yield no brand |
| Coverage thresholds | calibrated on the bundled bilingual sample | tune in `src/config.py` for other corpora |
