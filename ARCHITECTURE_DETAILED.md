# AISO Copilot — Detailed Architecture (Process & I/O Specification)

This document specifies **every process (stage) in the pipeline**, in execution
order, with its **task, input, and output contract**. It is the precise companion
to the narrative in [PROJECT_DEEP_DIVE.md](PROJECT_DEEP_DIVE.md) and the layer map
in [PIPELINE_AND_ARCHITECTURE.md](PIPELINE_AND_ARCHITECTURE.md).

**The pipeline = 19 stages, grouped into 4 phases**, all orchestrated by one
function: `run_analysis()` in `src/services/analyzer.py`. The three entry points
(Streamlit UI, FastAPI, CLI) all call that single function.

```text
PHASE A  Setup & Input        S0  S1
PHASE B  Extract & Understand  S2  S3  S4  S5  S6
PHASE C  Retrieve & Score      S7  S8  S9  S10 S11 S12
PHASE D  Outputs & Persist     S13 S14 S15 S16 S17 S18
```

Two cross-cutting **sub-systems** are documented separately at the end: the
**Retrieval engine** (inside S9) and the **LLM provider system** (used by S0, S7,
S15, S17).

Legend: **Mode** = `det` (deterministic, always runs) · `opt-LLM` (uses an LLM if
available, else deterministic fallback) · `opt` (runs only if input provided).

---

## Master table — all 19 stages

| # | Stage | Module · function | Input | Output | Mode | On failure |
|---|-------|-------------------|-------|--------|------|-----------|
| S0 | LLM provider resolution | `llm/provider_base.get_provider`, `build_openrouter_agents` | mode, api_key, model list | `(provider, status)`, `[agents]` | opt-LLM | → no-LLM provider |
| S1 | Input acquisition | `crawler/fetch_page`, `input/sample_loader`, `input/validators` | url \| paste \| sample | raw text + `effective_type` | det | structured error `{ok:false}` |
| S2 | Content extraction | `crawler/extract_content.extract_content` | raw, source_type, url | **page object** | det | empty fields, low extractability score |
| S3 | Readability metrics | `services/metrics.text_metrics` | `page.body_text` | readability dict | det | nulls |
| S4 | Entity & topic extraction | `audit/entity_extractor.extract_entities` | page, topic, audience | **entity_result** | det | empty categories |
| S5 | Structure audit | `audit/structure_audit.audit_structure` | page, entity_result | **structure_result** | det | low score + weaknesses |
| S6 | Topic/audience derivation | `analyzer._derive_topic` | user topic, entities, page | `(topic, audience)` strings | det | falls back to defaults |
| S7 | Query fan-out generation | `query/fanout_generator.generate_fanout` | topic, audience, seeds, entities, agents | **fanout** | opt-LLM | templates only |
| S8 | Chunking | `retrieval/chunker.build_chunks` | page | `[chunk]` | det | empty list |
| S9 | Coverage evaluation | `retrieval/hybrid_coverage.evaluate_coverage` | chunks, questions | **coverage** | det (+opt emb) | all Missing |
| S10 | Sourceability assessment | `audit/sourceability.assess_sourceability` | page, entity_result | **sourceability** | det | low score |
| S11 | Schema recommendation | `audit/schema_recommender.recommend_schema` | page, entity_result | **schema** | det | empty preview |
| S12 | Score combination | `audit/scoring.compute_scores` | the 5 audit outputs + technical | **scores** | det | clamped 0–100 |
| S13 | Search Console analysis | `search_console/csv_loader` + `opportunity_scoring` | CSV (optional) | opportunities + summary | opt | `{error}` in summary |
| S14 | n8n blueprint | `automation/n8n_blueprint_generator` | api url | **blueprint** | det | — |
| S15 | Answer simulation | `analyzer._simulate_answers` | coverage_matrix, provider | `[simulation]` | opt-LLM | template answers |
| S16 | Result assembly | `analyzer.run_analysis` | all above | **result object** | det | — |
| S17 | Executive summary | `reports/markdown_report.build_executive_summary` (+ LLM polish) | result | summary string | opt-LLM | template summary |
| S18 | Artifact persistence | `reports/*`, `services/session_store` | result | files on disk | det | in-memory only if `write_files=False` |

---

## PHASE A — Setup & Input

### S0 · LLM provider resolution
- **Task:** resolve the requested LLM mode into a usable provider for
  simulation/polish, and (OpenRouter only) build the multi-agent fan-out panel.
- **Input:** `llm_mode` (`no_llm`|`openrouter`|`ollama`), `openrouter_api_key`,
  `openrouter_model` (str|list), `ollama_base_url`, `ollama_model`.
- **Output:**
  ```text
  llm           : LLMProvider           # primary, for S15/S17
  llm_status    : str                   # human-readable, shown in UI
  fanout_agents : list[OpenRouterProvider]   # [] unless OpenRouter + key
  ```
- **Contract:** `provider.complete(prompt, system, max_tokens, temperature) ->
  str | None` — **never raises**. Missing key/model/server → `NoLLMProvider`
  (returns `None`, i.e. "use templates").

### S1 · Input acquisition
- **Task:** turn the chosen input mode into raw page content.
- **Input (one of):** `url`; `raw_content` (HTML/MD/text); `sample_name`.
- **Process:** URL → `validate_url` → `fetch_page` (HTTP GET, 15s timeout);
  paste → `validate_pasted_content` (size cap); sample → `load_sample`.
- **Output:** `raw: str`, `effective_type: html|markdown|text`, `input_meta`.
- **Failure:** returns `{ok: false, error, suggestion}` (e.g. "use paste mode").

---

## PHASE B — Extraction & Understanding

### S2 · Content extraction  *(the central contract)*
- **Task:** parse raw HTML/Markdown/text into one structured **page object** that
  every later stage consumes.
- **Input:** `raw`, `effective_type`, `url`.
- **Output — page object:**
  ```json
  {
    "source_type": "html|markdown|text", "url": "…|null",
    "title": "…", "meta_description": "…",
    "headings": {"h1": [], "h2": [], "h3": []},
    "body_text": "…",
    "sections": [{"heading","level","content","word_count"}],
    "links": {"internal": [{"text","href"}], "external": []},
    "faq_blocks": [{"question","answer"}],
    "json_ld": [], "json_ld_types": [], "json_ld_errors": [], "microdata_types": [],
    "noindex": false, "word_count": 0,
    "technical_extractability": {"status","score","issues": []},
    "extractor": "beautifulsoup|trafilatura+beautifulsoup|markdown|plaintext"
  }
  ```

### S3 · Readability metrics
- **Task:** basic readability stats.
- **Input:** `page.body_text`. **Output:** `{word_count, sentence_count,
  avg_sentence_words, long_sentence_count, flesch_reading_ease|null, note}`
  (Flesch skipped for Thai-dominant text). Attached as `page.readability`.

### S4 · Entity & topic extraction
- **Task:** extract the entities AI systems need to disambiguate the page.
- **Input:** page, `target_topic`, `target_audience`.
- **Output — entity_result:**
  ```json
  {
    "entities": {"brand","organization","services","products","industries",
                 "locations","audiences","problems","solutions","benefits",
                 "proof_points","metrics","tools"},   // each a list
    "entity_clarity_score": 0,                          // 0–100
    "score_breakdown": {"<category>": <weight earned>},
    "entity_gaps": ["…"], "recommendations": ["…"]
  }
  ```

### S5 · Structure audit
- **Task:** 24 weighted checks on AI-Search structure (titles, direct answers,
  FAQ, process, links, trust…).
- **Input:** page, entity_result.
- **Output — structure_result:**
  ```json
  {"structure_score": 0, "strengths": [], "weaknesses": [], "recommendations": [],
   "checks": [{"id","label","weight","passed","details"}]}
  ```

### S6 · Topic/audience derivation
- **Task:** fill missing topic/audience from detected entities or the H1.
- **Input:** user topic/audience, entity_result, page.
- **Output:** `topic: str`, `audience: str` (used by S7).

---

## PHASE C — Retrieve & Score (the core)

### S7 · Query fan-out generation
- **Task:** produce the question set an answer engine would explore.
- **Input:** topic, audience, `seeds`, entities, `agents` (S0), `llm`.
- **Process:** seeds → 18 templates → distinct-baseline comparison Qs → entity
  extras → optional multi-agent LLM extras (each agent few-shot, merged & deduped,
  per-agent capped). Cap = `MAX_FANOUT_QUESTIONS` (48).
- **Output — fanout:**
  ```json
  {"seed_questions": [], "llm_used": false, "llm_note": "…", "agents_used": [],
   "fanout_questions": [{"question","intent","source"}]}
  // intent ∈ 11 types; source ∈ seed|template|openrouter:<model>|ollama:<model>
  ```

### S8 · Chunking
- **Task:** split the page into retrievable passages (RAG ingest).
- **Input:** page. **Output:** `[{"id","section","text","word_count"}]`
  (~110-word target, heading prepended to each chunk; title+meta = one chunk).

### S9 · Coverage evaluation  *(retrieval engine — see sub-system below)*
- **Task:** per fan-out question, decide Covered/Partial/Missing with evidence.
- **Input:** chunks (S8), questions (S7).
- **Output — coverage:**
  ```json
  {
    "coverage_score": 0,            // 0–100 = 100·(covered + 0.5·partial)/total
    "method": "bm25(…) + tfidf(…) + term_overlap [+ embeddings(…)] [+ cross-lingual bridge]",
    "coverage_matrix": [{
      "question","intent","source",
      "coverage": "Covered|Partial|Missing", "score": 0.0,
      "evidence": [{"section","text","score"}],
      "gap": "…|null", "recommendation": "…|null"
    }]
  }
  ```

### S10 · Sourceability assessment
- **Task:** 15 weighted evidence checks — is the page quotable as a source?
- **Input:** page, entity_result.
- **Output — sourceability:** `{"sourceability_score", "strong_evidence": [],
  "missing_evidence": [], "recommendations": [], "checks": [{id,label,weight,passed,details}]}`.

### S11 · Schema recommendation
- **Task:** recommend schema.org types supported by visible content + build a
  copy-paste JSON-LD preview (nothing invented).
- **Input:** page, entity_result.
- **Output — schema:**
  ```json
  {"schema_score": 0, "recommended_schema_types": [], "existing_types": [],
   "missing_types": [], "json_ld_preview": {…}, "warnings": [], "notes": [],
   "score_parts": {"existing_markup","error_free","alignment_with_recommended","content_feasibility"}}
  ```

### S12 · Score combination
- **Task:** blend the six sub-scores into the overall readiness score and rank
  priority actions by weighted headroom.
- **Input:** structure_result, entity_result, coverage, sourceability, schema,
  `page.technical_extractability`.
- **Output — scores:**
  ```json
  {"overall_ai_search_readiness": 0,
   "subscores": {"structure","entity_clarity","query_coverage","sourceability","schema","technical_extractability"},
   "weights": {…},
   "priority_actions": [{"category","action","priority": "high|medium|low"}]}
  ```

---

## PHASE D — Outputs & Persistence

### S13 · Search Console analysis *(optional)*
- **Task:** turn a GSC performance CSV into ranked AI-search opportunities.
- **Input:** CSV path / upload / DataFrame.
- **Process:** `load_search_console_csv` (lenient column aliasing, %/comma
  normalization) → `find_opportunities` (5 precedence-ordered rules).
- **Output:** `opportunities: [{query,page,clicks,impressions,ctr,position,
  opportunity_type,secondary_signals,priority,reason,recommended_action}]`,
  `summary: {rows,total_clicks,total_impressions,avg_ctr,avg_position_weighted,by_type,…}`.
  On bad CSV: `summary = {"error": "…"}`.

### S14 · n8n blueprint generation
- **Task:** emit an automation blueprint (documentation only — no live n8n).
- **Output — blueprint:** `{workflow_name, project, description,
  nodes:[{type,name,purpose,config_hint}], connections:[[from,to]],
  n8n_import_skeleton:{…}, notes:[]}`.

### S15 · Answer simulation
- **Task:** for a sample of questions, simulate the engine's answer **using only
  retrieved evidence**; flag missing evidence.
- **Input:** coverage_matrix, primary `llm`.
- **Output:** `[{question,intent,simulated_answer,used_evidence:[{section,text}],
  missing_evidence:[],support_level: strong|medium|weak, generator}]`.
  Deterministic templates by default; first few use the LLM if active.

### S16 · Result assembly
- **Task:** compose the single result object (spec §10 + documented extras) and
  the limitations list.
- **Output — result object (top-level keys):**
  ```text
  ok, project, generated_at,
  input{source_type,url,sample_name,target_topic,target_audience,
        llm_mode,llm_active,llm_status,fanout_note,fanout_agents},
  page{…}, scores{…}, structure_audit{…}, query_fanout[], seed_questions[],
  coverage_matrix[], coverage_method, sourceability{…}, entities{…},
  schema_recommendations{…}, search_console_opportunities[], search_console_summary{…},
  n8n_blueprint{…}, answer_simulations[], priority_actions[], limitations[],
  executive_summary, report_markdown, generated_files[]
  ```

### S17 · Executive summary
- **Task:** build the report's executive summary (deterministic template), then
  optionally LLM-polish wording — facts/numbers unchanged.
- **Input/Output:** result → `executive_summary: str`.

### S18 · Artifact persistence  *(skipped if `write_files=False`)*
- **Task:** write deliverables to `outputs/`.
- **Output files:** `outputs/reports/AI_SEARCH_AUDIT_REPORT.md`,
  `outputs/reports/audit_result.json`,
  `outputs/workflows/n8n_workflow_blueprint.{md,json}`,
  `outputs/runs/run_<ts>_<slug>.json`. Paths returned in `result.generated_files`.

---

## Sub-system 1 — Retrieval engine (inside S9)

S9 runs a **per-question** loop. Three retriever objects are built **once** from
the chunks, then each question is scored against all chunks.

**Retriever objects (built from chunks):**

| Object | Backend | `score_all(query)` output |
|---|---|---|
| `BM25Retriever` | rank-bm25 → pure-Python Okapi | raw BM25 per chunk |
| `TfidfRetriever` | scikit-learn → pure-Python TF-IDF | cosine 0–1 per chunk |
| `EmbeddingRetriever` | sentence-transformers (default ON, multilingual) | cosine 0–1 per chunk, or `[]` if unavailable |

**Per-question process:**
```text
INPUT:  question{question,intent,source}, chunks
 1. detect cross_lingual = (question language != page language)
 2. expand query (cross-lingual only): + EN↔TH glossary bridge terms
 3. signals per chunk:
      term_overlap = covered concept-groups / total        (0–1)
      tfidf_cos    = TfidfRetriever.score_all(expanded q)   (0–1)
      bm25_sat     = bm25/(bm25+6)                           (0–1)
      emb_cos      = EmbeddingRetriever.score_all(q)         (0–1, if available)
 4. weights = select(cross_lingual, embeddings_available)   # 4 config blends
 5. blended = Σ weightᵢ · signalᵢ   (per chunk)
 6. best = max(blended); classify ≥0.55 Covered / ≥0.40 Partial / else Missing
 7. evidence = top-3 chunks ≥0.15; gap+recommendation if not Covered
OUTPUT: one coverage_matrix row
```

The four weight blends (`src/config.py`): monolingual, monolingual+emb,
cross-lingual, cross-lingual+emb — all data-tuned (see `evals/FINDINGS.md`).

## Sub-system 2 — LLM provider system (S0, S7, S15, S17)

```text
get_provider(mode, key, model, …) -> (provider, status)   # primary, 1 model
build_openrouter_agents(key, models) -> [provider, …]     # multi-agent panel
provider.complete(prompt, system, max_tokens, temp) -> str | None   # never raises
```

- **Modes:** `no_llm` (always available, returns `None`), `openrouter`
  (user key + free model slugs), `ollama` (local server).
- **Multi-agent (S7):** one provider per free model; each generates questions
  independently; results merged, deduped, per-model capped, tagged
  `openrouter:<model>`. One model failing never blocks the others.
- **Used only for:** extra fan-out questions, answer-simulation wording, summary
  polish. **Never for:** scoring, extraction, retrieval, schema. Any failure →
  deterministic path; the audit result is identical in shape.

---

## Control flow & failure matrix

| If this fails / is missing | Stage | Behavior |
|---|---|---|
| URL unreachable / blocked | S1 | `{ok:false}` + "use paste mode" |
| LLM key/model/server absent | S0/S7/S15/S17 | deterministic templates; `llm_active=false` |
| One OpenRouter model stale | S7 | that model skipped; others continue |
| sentence-transformers absent | S9 | embeddings dropped from blend; lexical only |
| rank-bm25 / scikit-learn absent | S9 | pure-Python retriever twins |
| PyThaiNLP absent | S2/S8/S9 | trigram tokenizer fallback |
| No Search Console CSV | S13 | stage skipped; section omitted |
| `write_files=False` | S18 | artifacts in-memory only (`report_markdown`) |

**Determinism guarantee:** with LLM off (default-safe) and embeddings fixed, the
same input always yields the same scores. Tests force `AISO_USE_EMBEDDINGS=0` so
the suite is deterministic regardless of environment.

## Entry points → pipeline

| Entry point | File | Maps to |
|---|---|---|
| Streamlit UI | `app/streamlit_app.py` | calls `run_analysis()`; renders 11 tabs from the result object |
| FastAPI | `api/server.py` | `/analyze` = full pipeline; `/fanout`=S7, `/coverage`=S8–S9, `/schema/recommend`=S2+S4+S11, `/report/generate`=S16–S17 |
| CLI | `python -m src.services.analyzer` | full pipeline, writes artifacts |

All three are thin wrappers — **no analysis logic lives in the entry points.**
