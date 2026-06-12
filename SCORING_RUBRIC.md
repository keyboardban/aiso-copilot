# Scoring Rubric

Every score in AISO Copilot is deterministic, weighted, and explainable. No LLM is
involved in any score. All constants live in `src/config.py`; check lists live in the
modules named below, and every check is returned in the result JSON with its weight,
pass/fail, and details.

## Overall AI Search Readiness

```text
overall = 0.20·structure + 0.15·entity_clarity + 0.25·query_coverage
        + 0.20·sourceability + 0.10·schema + 0.10·technical_extractability
```

Weights rationale: coverage and sourceability (45% combined) measure whether the page
can actually *answer and evidence* the questions AI systems ask — the heart of AI
Search readiness. Structure (20%) is the delivery vehicle. Schema and technical
extractability (10% each) are supporting machine-readability layers. Entity clarity
(15%) governs disambiguation. All sub-scores are clamped to 0–100.

Bands used in the report: ≥80 Strong · 60–79 Moderate · 40–59 Developing · <40 Needs
significant work.

---

## 1. Structure score (`src/audit/structure_audit.py`)

24 weighted checks, total weight **120**. `score = 100 · Σ(passed weights) / 120`.

| Check | Weight | Passes when |
|---|---:|---|
| Clear page title exists | 8 | non-empty title |
| Title length snippet-friendly | 2 | 15–70 chars |
| Meta description exists | 6 | non-empty |
| Meta description length | 2 | 70–170 chars |
| H1 exists | 8 | ≥1 H1 |
| Exactly one H1 | 3 | count == 1 |
| Descriptive H2/H3 | 6 | ≥3 subheadings of 2–12 words |
| Direct answer-style blocks | 8 | ≥2 sections opening with a definition pattern or answering a question heading |
| Explicit definitions | 6 | "X is…", "also called…", "refers to…", "คือ" present |
| FAQ / Q&A content | 8 | ≥2 detected Q&A blocks |
| FAQ depth | 3 | ≥4 blocks, ≥3 with 25+ word answers |
| Internal links | 5 | ≥2 |
| External reference links | 4 | ≥1 |
| Service/product identifiable | 6 | service/product entities found |
| Brand named and visible | 6 | brand detected AND appears in title/body |
| Audience named | 5 | audience entities found |
| Location/market named | 3 | location entities found |
| Concrete examples | 5 | "for example / such as / เช่น" |
| Process / steps section | 6 | ≥3 numbered/step headings, a process section with ≥3 subsections, or ≥3 ordered-list lines |
| Metrics present | 5 | ≥2 numeric facts (%, x, CTR/KPI/ROI terms) |
| Case studies / client proof | 4 | case-study/testimonial patterns |
| Trust signals | 4 | about/contact/team links or credential language |
| JSON-LD present | 4 | ≥1 parsed block |
| Schema matches visible text | 3 | schema `name` values appear in visible content, no parse errors |

Outputs: `strengths` (passed, weight ≥5), `weaknesses` (all failed, by weight),
`recommendations` (one per failed check), `checks` (full table).

## 2. Entity clarity score (`src/audit/entity_extractor.py`)

11 weighted categories, weights sum to **100**; a category scores its full weight when
at least one entity is detected (presence-based — the score answers "is this stated at
all?", not "how often?"):

brand 15 · services 15 · audiences 12 · problems 10 · solutions 10 · benefits 8 ·
proof_points 8 · locations 6 · industries 6 · metrics 6 · tools 4

`products` and `organization` are extracted but deliberately unweighted (service pages
without products must not be penalized). Detection: JSON-LD names → title suffix →
domain (brand); curated lexicons (services, industries, locations, audiences, tools);
sentence patterns (problems, solutions, benefits, proof, metrics). The per-category
breakdown ships in the result as `score_breakdown`.

## 3. Query coverage score (`src/retrieval/hybrid_coverage.py`)

Per question, against section-based chunks:

```text
term_overlap = |question content-terms found in chunk| / |question content-terms|
tfidf        = cosine(question, chunk)                       # 0..1
bm25_sat     = bm25_raw / (bm25_raw + 6)                     # 0..1
blended      = 0.40·term_overlap + 0.35·tfidf + 0.25·bm25_sat
               (with local embeddings enabled: 0.30/0.25/0.20 + 0.25·emb_cosine)
```

Best-chunk blended score classifies the question:

| Class | Threshold | Meaning |
|---|---|---|
| **Covered** | ≥ 0.55 | strong, question-specific evidence exists |
| **Partial** | ≥ 0.40 | related evidence, incomplete answer |
| **Missing** | < 0.40 | topic-level mention at best |

Calibration note: questions that merely share the page's topic phrase land at
~0.30–0.40 blended, so the Partial floor (0.40) deliberately sits above that band —
*mentioning the topic is not answering the question.*

```text
coverage_score = 100 · (covered + 0.5·partial) / total_questions
```

Thai questions are matched via character trigrams; a Thai term counts as "present"
when ≥50% of its trigrams appear in the evidence chunks.

## 4. Sourceability score (`src/audit/sourceability.py`)

15 evidence checks, weights sum to **100**:

| Check | Weight |
|---|---:|
| Clear definition of the core topic | 10 |
| Step-by-step process | 10 |
| Metrics / measurable outcomes (≥2 numeric facts) | 10 |
| Case study or client proof point | 10 |
| Specific examples | 8 |
| Identifiable author or organization | 8 |
| Named methodology / framework | 6 |
| Comparison explanation | 6 |
| Visible date / freshness signal | 6 |
| External references | 6 |
| Links to about/contact pages | 5 |
| Internal links to supporting content (≥3) | 5 |
| Structured data present | 5 |
| Visible content supports the structured data | 3 |
| Title and H1 name the same topic (low ambiguity) | 2 |

Each failed check reports *why it matters for citation* (`missing_evidence`) and a
concrete fix (`recommendations`).

## 5. Schema score (`src/audit/schema_recommender.py`)

```text
schema_score = existing_markup (25 if any JSON-LD parses)
             + error_free      (10 if JSON-LD present with zero parse errors)
             + alignment       (35 · |existing ∩ recommended| / |recommended|)
             + feasibility     (30 · supported_signals / 4)
```

`supported_signals` (what the visible content could back): brand identified · service
or product identified · ≥2 substantive FAQ blocks · meta description present. A page
with rich content but no markup tops out around 30 (feasibility only) — by design,
because the score measures *deployed* machine-readability. Recommended types are
gated by visible content (e.g. LocalBusiness requires a visible phone/address;
FAQPage requires ≥2 real Q&A blocks), and the JSON-LD preview is built exclusively
from extracted page content. The additive parts ship as `score_parts`.

## 6. Technical extractability score (`src/crawler/extract_content.py`)

Starts at 100, deducts per issue, clamps to 0–100:

| Issue | Deduction |
|---|---:|
| Extractable text < 120 words | −30 |
| Extractable text < 300 words | −15 |
| `noindex` robots meta | −20 |
| Very low text-to-HTML ratio (<5%, page >20 KB — likely JS-rendered) | −15 |
| No title | −10 |
| No H1 | −10 |
| No heading structure at all | −10 |
| No meta description | −8 |
| JSON-LD parse error (max 2 counted) | −8 each |
| Input truncated at the size cap | −5 |

Status: ≥80 ok · ≥55 warning · else poor.

## Priority actions (`src/audit/scoring.py`)

Categories are ranked by **weighted headroom** `(100 − subscore) · weight` — i.e. where
improvement buys the most overall score — then each contributes its top concrete
recommendations (including the actual unanswered questions for coverage). Priority
labels come from the source sub-score: <50 high · <70 medium · else low. Capped at 8
actions, deduplicated.

## Limitations of this scoring

- Presence-based checks measure *whether* something is stated, not how well — a weak
  case study passes the case-study check.
- Coverage is lexical/statistical (BM25, TF-IDF, n-grams). Synonym-heavy answers can
  under-score without the optional embedding layer; boilerplate keyword stuffing can
  over-score term overlap.
- Thresholds (0.55 / 0.40) were calibrated on the bundled bilingual sample corpus;
  they are config constants, not universal truths.
- Scores compare a page against content-shape heuristics, not against live AI-engine
  behavior. Treat them as a structured review aid, not a ranking prediction.
