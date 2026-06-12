# AISO Copilot — User Guide

A page-by-page guidebook for the dashboard: what every input does, what every tab
shows, how the numbers are calculated, and how to read the results.

**The 60-second version:** open the app, keep **Sample Demo** selected in the sidebar,
click **Analyze AI Search Readiness**, and explore the tabs from left to right. Nothing
else is required — no API key, no internet, no setup.

---

## Table of contents

1. [The sidebar — your inputs](#1-the-sidebar--your-inputs)
2. [Tab: Overview](#2-tab-overview)
3. [Tab: Structure Audit](#3-tab-structure-audit)
4. [Tab: Query Fan-out](#4-tab-query-fan-out)
5. [Tab: Coverage Matrix](#5-tab-coverage-matrix)
6. [Tab: Sourceability](#6-tab-sourceability)
7. [Tab: Entities](#7-tab-entities)
8. [Tab: Schema](#8-tab-schema)
9. [Tab: Search Console](#9-tab-search-console)
10. [Tab: n8n Blueprint](#10-tab-n8n-blueprint)
11. [Tab: Report](#11-tab-report)
12. [Tab: Raw JSON](#12-tab-raw-json)
13. [Reading the scores](#13-reading-the-scores)
14. [Common workflows](#14-common-workflows)
15. [Troubleshooting](#15-troubleshooting)

---

## 1. The sidebar — your inputs

Everything you control lives in the left sidebar. Only one thing is truly required:
**some content to analyze**. Every other field improves the audit but has a sensible
fallback.

### Input mode

| Mode | When to use it | What to enter |
|---|---|---|
| **Sample Demo** | First run, demos, testing | Nothing — pick one of the two bundled sample pages. `sample_page.md` is the plain-content version; `sample_page.html` is the same page with partial JSON-LD markup (useful to see how existing schema changes the scores). |
| **Paste HTML / Markdown / Text** | The most reliable way to audit a real page | Copy your page's content and paste it. For best results paste the full HTML (right-click the page → *View Page Source* → copy everything). Markdown or plain text also work. Leave format on **Auto-detect** unless it guesses wrong. |
| **URL** | Quick audits of live pages | A full URL like `https://example.com/services/seo`. Fetching is best-effort: sites that block bots or render everything in JavaScript will fail — the app will tell you and suggest paste mode instead. |

### Target topic *(recommended)*

The main subject of the page, used to generate fan-out questions
(e.g. *"What is {topic}?"*, *"How is {topic} different from SEO?"*).

- **Enter:** a short noun phrase — `AI Search Optimization`, `solar panel
  installation`, `dental implants Bangkok`.
- **If you leave it empty:** the app derives a topic from the detected service
  entities or the page's H1. Explicit is better — a precise topic makes the question
  set sharper.

### Target audience *(recommended)*

Who the page is trying to reach. Used in audience-flavored questions
(*"Why is {topic} important for {audience}?"*).

- **Enter:** e.g. `Thai SMEs`, `marketing managers`, `hotel owners in Phuket`.
- **If empty:** falls back to the first audience detected on the page, then to
  the generic "businesses".

### Seed questions *(optional, one per line)*

Real questions your customers ask — from sales calls, support tickets, or keyword
research. They are added to the generated question set, classified by intent, and
checked for coverage exactly like the template questions. Thai and English both work.

```text
AI Search Optimization คืออะไร
How long does it take to see results?
Do you work with e-commerce brands?
```

Leave it empty to rely on the 20+ built-in templates alone.

### Search Console (optional)

Upload a **CSV export** of Google Search Console's *Performance* report — no API, no
login. Required columns (header names are matched leniently):

```csv
query,page,clicks,impressions,ctr,position
```

To export from GSC: Performance → Search results → Export → Download CSV → use the
"Queries" sheet (add the page column if you can). Or tick **Use bundled sample CSV**
to see the feature with demo data.

### LLM mode

| Option | What it does | What you need |
|---|---|---|
| **No LLM (default)** | The complete audit, fully deterministic | Nothing |
| **OpenRouter** | Adds extra fan-out questions, nicer answer simulations, and a polished executive summary | An OpenRouter API key **and** a model slug you choose (pick a free one — slugs ending in `:free` on openrouter.ai/models) |
| **Ollama** | Same extras, fully local | A running Ollama server; model field can stay empty (first installed model is used) |

**Important:** LLMs never touch the scores. If the key is missing or the model errors
out, the app silently continues in deterministic mode and tells you so in the
Overview tab's status line.

### The Analyze button

Runs the whole pipeline (typically 2–5 seconds). Results stay on screen until you
analyze again. Each run also writes files to `outputs/` (report, JSON, n8n blueprint).

---

## 2. Tab: Overview

**What it shows:** the executive view — one gauge, six bars, and a to-do list.

- **Gauge (Overall AI Search Readiness, 0–100):** a weighted blend of the six
  sub-scores. Color = band: green ≥ 80 (Strong), blue 60–79 (Moderate), ochre 40–59
  (Developing), red < 40 (Needs work).
- **Questions covered / Word count:** quick context for the gauge.
- **Subscore bars:** each dimension with its weight in the blend. The bar color uses
  the same bands, so a red bar is your biggest problem at a glance. Weights:
  query coverage 25%, structure 20%, sourceability 20%, entity clarity 15%,
  schema 10%, technical extractability 10%.
- **Priority actions:** the ranked to-do list. Items are ordered by *weighted
  headroom* — how many overall points fixing that area can buy. HIGH = the source
  score is below 50, MEDIUM = below 70, LOW = polish.
- **Executive summary / Limitations** (expanders): the summary that also appears in
  the exported report, and the honest list of what this tool does *not* measure.

**How to read it:** start with the reddest bar, then do the priority actions top to
bottom. The status line under the heading tells you which LLM mode actually ran.

---

## 3. Tab: Structure Audit

**What it shows:** whether the page is *shaped* for AI consumption — 24 weighted
checks on titles, headings, answer blocks, FAQ, links, and trust signals.

- **Strengths / Weaknesses:** the passed and failed checks, most important first
  (each check's weight determines its importance; the full table is in the expander
  at the bottom).
- **Recommendations:** one concrete fix per failed check.
- **Title & meta preview:** how the page's title/description pair looks as a search
  snippet. Missing meta description shows up here immediately.
- **Extracted headings:** the H1/H2/H3 outline the parser saw. If this looks wrong
  (missing sections, junk navigation text), the audit is working with bad input —
  consider pasting cleaner HTML.
- **All structure checks (expander):** every check with its weight, pass/fail, and
  details — this is the full receipt behind the structure score.

**What it means:** AI systems retrieve *passages*, not pages. Question-style headings
followed by direct answers, a real FAQ, and one clear H1 make passages quotable.
A page can have great content and still fail here because the content is buried in
walls of text.

---

## 4. Tab: Query Fan-out

**What it shows:** the question set an AI assistant would plausibly explore around
your topic — the questions your page will be *judged against* in the Coverage tab.

- **Table:** every generated question with its **intent** (definition, comparison,
  implementation, measurement, commercial, technical, trust, local, schema, proof,
  content_strategy) and **source**:
  - `seed` — you typed it in the sidebar
  - `template` — generated from the 20+ built-in patterns using your topic/audience
  - `openrouter` / `ollama` — added by the optional LLM
- **Intent distribution / Question sources:** bar charts of how the set is composed.

**What it means:** when someone asks an assistant one question, the system internally
"fans out" into related sub-questions before composing an answer. A page that covers
the fan-out — not just the headline query — is a page that keeps showing up as
evidence.

**Inputs that change this tab:** topic, audience, seed questions, and (if entities
were detected) your brand and market get their own questions.

---

## 5. Tab: Coverage Matrix

**What it shows:** for each fan-out question — can this page answer it, and where's
the proof? This is the heart of the audit.

- **Stacked bar:** the Covered / Partial / Missing split at a glance.
- **Main table:** one row per question with a colored status, the intent, an
  **evidence score** progress bar (0–1), and which page sections supplied the
  evidence.
- **Content gaps:** expanders for each Partial/Missing question showing the **gap**
  (what's not addressed, including the specific missing terms), a **recommendation**
  (what content to add, tailored to the question's intent), and the **best evidence
  found** (actual passages with their match scores). Switch the radio to *All
  questions* to inspect Covered ones too.
- **Simulated AI answers:** for a sample of questions, how an answer engine might
  respond *using only this page*. Strong/medium/weak support mirrors
  Covered/Partial/Missing. In no-LLM mode these are honest evidence stitches; with an
  LLM they read more naturally but are still restricted to page evidence.

**How the classification works (no LLM involved):** each question is scored against
the page's passages by a blend of three deterministic signals — term overlap (are the
question's content words actually on the page?), TF-IDF cosine similarity, and BM25.
Blended score ≥ 0.55 → **Covered**, ≥ 0.40 → **Partial**, below → **Missing**. The
Partial floor is deliberately set above what a question earns just by mentioning the
page's topic: *mentioning the topic is not answering the question.*

**What to do with it:** every Missing question with real search demand is a content
brief. The recommendation text tells you what shape the answer should take.

---

## 6. Tab: Sourceability

**What it shows:** citation readiness — does the page contain enough explicit,
quotable evidence for an AI system to use it as a *source*? 15 weighted checks
totalling 100 points.

- **Score + present/missing bars:** how many evidence points the page earned vs left
  on the table.
- **Strong evidence:** what the page already offers (definitions, steps, named
  methodology…).
- **Missing evidence:** each failed check **with the reason it matters for
  citation** — e.g. "Concrete numbers are citation currency — vague claims cannot be
  quoted as facts."
- **Recommendations:** the fixes, biggest weights first.

**What it means:** generated answers are assembled from quotable fragments. A page
that says "we improve your visibility" gives an assistant nothing to quote; a page
that says "typical projects see results within 3–6 months across 40+ clients" does.
This tab measures the *presence* of such evidence (it cannot verify truthfulness —
that stays your job).

---

## 7. Tab: Entities

**What it shows:** whether machines can tell *who you are, what you sell, for whom,
and where* — 13 entity categories extracted by deterministic rules (JSON-LD, lexicons,
sentence patterns).

- **Score + points-at-stake chart:** one bar per category. Bar length = how many of
  the 100 clarity points that category is worth; green = detected on the page (points
  earned), red = not detected (points missed). Each category is all-or-nothing, so
  **the longest red bars are your most valuable fixes**. Weights: brand 15,
  services 15, audiences 12, problems 10, solutions 10, benefits 8, proof points 8,
  locations 6, industries 6, metrics 6, tools 4 (products/organization are shown but
  unweighted).
- **Table:** what was actually detected per category — verify this! If your brand is
  missing or wrong, the page (not the tool) is being ambiguous.
- **Gaps / Recommendations:** the empty categories that matter most, and how to fix
  them.

**What it means:** entity ambiguity is an AI-search killer. If a system can't
confidently resolve "who is this page about", it won't recommend you. The fix is
almost always embarrassingly simple: *say it explicitly in the visible text*.

---

## 8. Tab: Schema

**What it shows:** structured-data status and a ready-to-use JSON-LD draft.

- **Existing / Recommended / Missing types:** what markup the page has vs what its
  visible content could support (Organization, Service, FAQPage, Article,
  BreadcrumbList, LocalBusiness).
- **JSON-LD preview:** copy-paste-ready markup built **strictly from content the
  page already shows** — names, descriptions, FAQ pairs, locations. Nothing is
  invented; that's why some fields you might expect are absent. Paste it into a
  `<script type="application/ld+json">` tag after review.
- **Warnings:** always shown, always worth reading — schema must mirror visible
  content, should be validated with Google's Rich Results Test, and does not
  guarantee visibility.
- **Notes:** why something was *not* recommended (e.g. LocalBusiness needs a visible
  address/phone first).
- **Score breakdown (expander):** the four additive parts — existing markup (25),
  error-free (10), alignment with recommendations (35), content feasibility (30).

**What it means:** a score of ~30 with rich content usually means one thing: the
content could support markup but none is deployed. Adding the previewed JSON-LD is
typically the single fastest score improvement in the whole audit.

---

## 9. Tab: Search Console

**What it shows:** (only when you provided a CSV) which of your real queries are
AI-search opportunities.

- **Totals row:** queries, clicks, impressions, average CTR, impression-weighted
  average position.
- **Opportunity landscape (scatter):** every opportunity plotted as position (x,
  left = better) vs CTR (y); bubble size = impressions, color = priority. The
  worrying cluster is **big red bubbles middle-left**: lots of impressions, decent
  position, almost no clicks — classic "an answer box is eating your clicks"
  territory and prime fan-out material.
- **Opportunity table:** one primary opportunity per query, with the reasoning and a
  recommended action. Types:

| Type | Trigger | Typical action |
|---|---|---|
| `intent_mismatch` | commercial query landing on a blog page | route it to a service page |
| `high_impression_low_ctr` | ≥500 impressions, CTR <1.5%, position ≤20 | rewrite title/meta, add a direct-answer block |
| `low_ctr_despite_rank` | top-5 position but CTR <2% | align title/meta with the query promise |
| `striking_distance` | position 8–20 | add a dedicated section answering the query |
| `ai_answer_opportunity` | question-style query | question heading + 2–3 sentence answer, FAQ markup |

**What to enter:** a GSC Performance CSV (see sidebar section above). The parser
tolerates `%` signs, thousands separators, and most GSC header variants.

---

## 10. Tab: n8n Blueprint

**What it shows:** a generated automation blueprint for running this audit as a
recurring agency workflow: webhook → AISO Copilot API → Google Sheets log → Google
Docs report → team notification → follow-up task.

- **Flow + node table:** each step with its purpose and setup hint.
- **Blueprint JSON (expander):** includes an n8n-import-style skeleton.

**What it means / doesn't mean:** this is *documentation*, not a live integration —
nothing connects to n8n from this app. To use it: run the FastAPI backend
(`uvicorn api.server:app --port 8000`), import the skeleton into your own n8n
instance, fill in credentials, and keep the human-review step before anything
reaches a client. The files are also written to `outputs/workflows/`.

**Input needed:** none — it's generated on every run.

---

## 11. Tab: Report

**What it shows:** the client-deliverable, and all the export buttons.

- **Four downloads:** the audit report (`.md`), the full result (`.json`), and the
  n8n blueprint (`.md` / `.json`).
- **Below the divider:** a full preview of the markdown report — executive summary,
  score breakdown, strengths, priority issues, the content gap matrix, sourceability,
  entities, schema (with the JSON-LD), Search Console opportunities, action plan,
  and limitations.

**How to use it:** the `.md` report pastes cleanly into Google Docs/Notion for client
delivery; the `.json` is for your own tooling or archiving. The same files are also
written to `outputs/reports/` on disk.

---

## 12. Tab: Raw JSON

**What it shows:** the complete analysis object — every check, every score component,
every evidence snippet, exactly as produced by the pipeline (the report markdown is
omitted for readability).

**Who it's for:** debugging, building on top of the tool, or verifying any number you
see elsewhere in the UI. Every score in the app can be traced to fields here; the
formulas live in [SCORING_RUBRIC.md](SCORING_RUBRIC.md).

---

## 13. Reading the scores

| Band | Range | Interpretation |
|---|---|---|
| **Strong** | 80–100 | Ready — maintain and extend |
| **Moderate** | 60–79 | Solid base, clear gaps — do the priority actions |
| **Developing** | 40–59 | Significant restructuring needed |
| **Needs work** | 0–39 | Start with fundamentals (usually content volume or extractability) |

Three honest caveats, always:

1. Scores are **estimated readiness**, not predictions of rankings or citations.
2. Checks measure **presence**, not quality — a weak case study still passes the
   case-study check.
3. The audit sees **one page**. Site authority, backlinks, and off-page brand
   mentions are out of scope.

## 14. Common workflows

**First demo (zero setup):** Sample Demo → Analyze → read Overview → open Coverage
Matrix and inspect a Missing question's gap and recommendation.

**Audit your own page:** Paste mode with full HTML → set topic + audience → paste
5–10 real customer questions as seeds → Analyze → export the report from the Report
tab. Fix the HIGH actions, re-paste the revised page, and compare scores.

**Monthly content planning with GSC data:** upload your Performance CSV alongside the
page → Search Console tab → take every `ai_answer_opportunity` and `striking_distance`
query → add them as seed questions on the relevant page's next audit → the Coverage
Matrix tells you exactly which ones the page can't answer yet.

**Compare markup impact:** run `sample_page.md` and `sample_page.html` back to back —
identical content, but the HTML version ships partial JSON-LD. Watch the Schema score
move from ~30 to ~77.

## 15. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "Could not fetch this URL" | site blocks bots, JS-rendered, offline | use Paste mode with View-Source HTML |
| Scores look too low for a good page | parser saw little text (check the headings list and word count) | paste cleaner HTML; check the Structure tab's extracted headings |
| Everything is "Partial" | questions only share the topic phrase with the page | add direct, self-contained answer passages — see each gap's missing terms |
| "OpenRouter selected but no API key…" | key/slug missing | fill both sidebar fields, or accept the (fully functional) deterministic fallback |
| Search Console tab says CSV problem | missing `query` column or unreadable file | export the Queries sheet from GSC Performance; check the header row |
| Thai questions score oddly | Thai matching is trigram-based (approximation) | expected behavior — see MODEL_AND_LIMITATIONS.md |

---

*Related docs: [README.md](README.md) (setup) · [SCORING_RUBRIC.md](SCORING_RUBRIC.md)
(every formula) · [MODEL_AND_LIMITATIONS.md](MODEL_AND_LIMITATIONS.md) (what the tool
can and cannot infer) · [PIPELINE_AND_ARCHITECTURE.md](PIPELINE_AND_ARCHITECTURE.md)
(how it's built).*
