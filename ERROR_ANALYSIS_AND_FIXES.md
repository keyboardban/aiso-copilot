# Error Analysis & Fixes — Cross-Lingual Retrieval

**Branch:** `experiment/pythainlp-tokenizer-fewshot`
**Context:** After switching Thai tokenization to PyThaiNLP `newmm`, an audit run
on a **Thai-language webpage with English fan-out questions** surfaced four
defects that collapsed coverage scores. This document records the error
analysis, the root cause of each, the fix, and the verification.

> **Free-first constraint that shaped the fixes:** there is no paid translation
> API in this project. So the cross-lingual fix is a deterministic domain
> **glossary + intent-cue bridge**, not machine translation — consistent with
> the lexicon-driven design used elsewhere (`entity_extractor.py`). All
> cross-lingual logic is scoped to fire **only when the question language differs
> from the page language**, so monolingual (English-on-English) behavior is
> byte-identical and all prior tests still pass.

---

## Summary

| # | Problem | Severity | Status |
|---|---------|----------|--------|
| 1 | Cross-lingual mismatch: English questions score ~0 against Thai content | High | Fixed |
| 2 | Comparison template duplicates the topic ("SEO vs SEO") | Medium | Fixed |
| 3 | HTML extractor mashes layout text ("DATA-LEDCREATIVE-POWERED") | Medium | Fixed |
| 4 | No semantic route for mixed-language chunks | Medium | Fixed (opt-in) |

**Headline result** — English fan-out questions audited against a Thai SEO page:

| Metric | Before | After |
|---|---|---|
| Coverage score | 5 / 100 | **32 / 100** |
| Missing questions | 18 / 20 | **9 / 20** |
| Covered | 0 | **2** |
| Partial | 2 | **9** |

(Deterministic bridge only, no embeddings. Enabling a multilingual embedding
model lifts this further — see Fix 4.)

---

## Problem 1 — Cross-lingual retrieval mismatch

**Symptom.** Fan-out questions are generated in English ("What is SEO?",
"How do you measure SEO?") while the audited page is predominantly Thai. BM25,
TF-IDF, and term-overlap all compare surface tokens, so English query terms
(`definition`, `measure`, `services`) never match Thai page tokens
(`ความหมาย`, `วัดผล`, `บริการ`). Most questions scored near zero.

**Root cause.** The retrieval query *was* the raw question string, and overlap
was computed over the question's literal terms. Nothing bridged the two
languages. (Proper nouns kept in Latin, like "SEO", matched — which is why a
couple of questions were Partial rather than all zero.)

**Fix — deterministic bilingual bridge** (`src/query/bilingual.py`, new):
- A domain glossary `EN_TO_TH` (SEO / AI-search / marketing terms) with an
  auto-built reverse map `TH_TO_EN`, plus per-intent cue words in both languages
  (`INTENT_CUES_TH` / `INTENT_CUES_EN`).
- In `hybrid_coverage.evaluate_coverage`, when a question is cross-lingual to the
  page:
  1. **Query expansion** — the BM25/TF-IDF query is enriched with the page-
     language equivalents of the question's content terms and intent cues
     (`bridge_terms`), so lexical retrieval can find Thai chunks.
  2. **Concept-group overlap** — each content term becomes a group
     `{term, cross-language equivalents…}`; a group counts as covered if *any*
     member appears. An extra group of page-language intent cues is added so a
     page that answers the intent in its own words still registers
     (`_concept_groups`).

The target output the analysis asked for —
`"SEO definition meaning คืออะไร ความหมาย รับทำ SEO"` — is exactly what the
expanded retrieval query now looks like.

**Scope guard.** `cross_lingual = (question_is_thai != page_is_thai)`, where the
page is "Thai" when ≥30% of its chunks contain Thai script. When false, groups
collapse to `{term}` and no expansion happens → identical to the old code path.

---

## Problem 2 — Duplicate entity in comparison questions

**Symptom.** For `topic = "SEO"`, the comparison fan-out produced
*"How is SEO different from SEO?"* — a meaningless, redundant query.

**Root cause.** Two comparison templates hardcoded their comparison target:
`"How is {topic} different from SEO?"` and `"… traditional search optimization?"`.
When the audited topic *was* one of those targets, entity A == entity B.

**Fix** (`src/query/templates.py`, `src/query/fanout_generator.py`):
- Removed the hardcoded comparison templates from `TEMPLATE_QUESTIONS`.
- Added `COMPARISON_TEMPLATE` + a `COMPARISON_BASELINES` list and a
  `comparison_alts(topic, limit)` helper that returns baselines **guaranteed
  distinct** from the topic (rejects any baseline equal to, contained in, or
  containing the topic, case-insensitive; falls back to a generic phrase if all
  collide).
- Fan-out now generates comparison questions from those distinct baselines.

Result: `topic="SEO"` → *"How is SEO different from traditional search
optimization?"* and *"… traditional digital marketing?"* — never "SEO vs SEO".

---

## Problem 3 — Mashed / concatenated tokens from the extractor

**Symptom.** The extractor merged distinct layout elements with no separator,
e.g. `DATA-LEDCREATIVE-POWEREDOUTCOME-DRIVEN`. `newmm` then treats the blob as
one unsegmentable string and exact keyword lookups fail.

**Root cause.** `BeautifulSoup.get_text()` was called without a separator on
headings and list items (`extract_content.py`), so adjacent inline children
(`<span>…</span><span>…</span>`) concatenated directly.

**Fix (two layers):**
1. **Root cause** (`src/crawler/extract_content.py`) — use
   `get_text(separator=" ")` for headings, list items, and link text, so inline
   children are space-separated. `DATA-LEDCREATIVE-POWERED` → `DATA-LED CREATIVE-POWERED`.
2. **Robustness backstop** (`hybrid_coverage._term_present`) — for meaningful
   Latin terms (length ≥ 4, or a whitelisted acronym like `seo`/`geo`/`llm`),
   accept a **substring hit inside a clearly-longer token**, so a residual
   `seoservices` still matches `seo`. Guards (length, whitelist, size gap)
   prevent false positives like `ai` inside `maintain`.

---

## Problem 4 — No semantic route for mixed-language chunks

**Symptom.** Even with the deterministic bridge, vocabulary that isn't in the
glossary won't match across languages by lexical means alone.

**Root cause.** Lexical retrieval (BM25/TF-IDF/overlap) is inherently
surface-form; only embeddings capture cross-lingual *meaning*, and the default
embedding model (`all-MiniLM-L6-v2`) is English-centric.

**Fix** (`src/config.py`, `src/retrieval/hybrid_coverage.py`, `.env.example`):
- When a question is cross-lingual **and** local embeddings are enabled, the
  blend switches to `COVERAGE_WEIGHTS_CROSSLINGUAL_EMB`
  (`embeddings: 0.65`, lexical signals demoted) so semantic similarity drives
  the score past the 0.40 Partial threshold, as the analysis requested.
- Embeddings score the **original** question (a multilingual model bridges
  languages without expansion); lexical signals score the **expanded** query.
- Documented the recommended free multilingual model
  (`paraphrase-multilingual-MiniLM-L12-v2`) in config and `.env.example`. When
  embeddings are off, the `method` string tells the user to enable it for best
  cross-lingual recall — no silent degradation.

This stays opt-in (embeddings are off by default, per the project's free-first,
no-download default). The deterministic bridge (Fix 1) handles the default path.

---

## Files changed

| File | Change |
|---|---|
| `src/query/bilingual.py` *(new)* | EN↔TH glossary, intent cues, `bridge_terms`/`equivalents`/`intent_cues` |
| `src/query/templates.py` | comparison baselines + `comparison_alts()` dedup |
| `src/query/fanout_generator.py` | generate comparison questions from distinct baselines |
| `src/crawler/extract_content.py` | `get_text(separator=" ")` for headings / list items / links |
| `src/retrieval/hybrid_coverage.py` | cross-lingual detection, query expansion, concept-group overlap, substring fallback, embedding-weight routing |
| `src/config.py` | `COVERAGE_WEIGHTS_EMB`, `COVERAGE_WEIGHTS_CROSSLINGUAL_EMB`, multilingual model constant |
| `.env.example` | multilingual embedding model guidance |
| `tests/test_crosslingual.py` *(new)* | 6 tests covering all four fixes |

## Verification

```bash
pytest -q          # 38 passed (32 original + 6 new); monolingual unchanged
```

- **Check 2:** `topic="SEO"` no longer yields "SEO vs SEO"; baseline-collision
  case (`topic="traditional search optimization"`) skips the colliding baseline.
- **Check 3:** mashed `<span>` headings extract spaced; `seoservices` matches `seo`,
  `maintain` does not match `ai`.
- **Check 1:** English questions on a Thai page — coverage **5 → 32**, Missing
  **18 → 9**, method reports `cross-lingual bridge`.
- **Check 4:** cross-lingual + embeddings switches to the semantic-heavy blend;
  multilingual model documented.
- **No regression:** Thai-on-Thai and English-on-English audits do not trigger
  the cross-lingual path; all pre-existing tests pass unchanged.

## Remaining limitations

- The bilingual glossary is domain-scoped (SEO / AI-search / marketing). Terms
  outside it rely on shared Latin tokens or the optional embedding route.
- Best cross-lingual recall needs the multilingual embedding model enabled
  (`AISO_USE_EMBEDDINGS=1` + `AISO_EMBEDDING_MODEL=…multilingual…`); the default
  deterministic path improves but does not fully solve semantic matching.
- The substring backstop is intentionally conservative (length/whitelist
  guarded) and is a safety net, not a replacement for clean extraction.
