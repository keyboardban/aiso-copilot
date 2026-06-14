# Cross-lingual coverage weight tuning — findings

**Question:** should the deterministic coverage blend re-weight when the question
language differs from the page language (bilingual mismatch)?

**Method:** `evals/run_crosslingual_eval.py` over `evals/crosslingual_dataset.py`
— 21 hand-labeled judgments (Thai page × English questions, and one English page
× Thai questions). Each judgment is an author call of Covered / Partial / Missing
based on whether the page's visible content answers the question. Deterministic
path only (no embeddings — the case in question). Thresholds held fixed at the
monolingual 0.55 / 0.40 to isolate the weight effect.

## Result — yes, re-weight toward term_overlap

| Blend (overlap/tfidf/bm25) | Exact acc. | Ordinal MAE | Answerable recall | Covered↔Missing flips |
|---|---:|---:|---:|---:|
| current 0.40 / 0.35 / 0.25 | 42.9% | 0.67 | 64.3% | 2 |
| 0.55 / 0.25 / 0.20 | 52.4% | 0.57 | 78.6% | 2 |
| **0.60 / 0.25 / 0.15 (adopted)** | **57.1%** | **0.52** | **78.6%** | 2 |
| 0.70 / 0.20 / 0.10 | 52.4% | 0.57 | 78.6% | 2 |
| 1.00 / 0.00 / 0.00 | 47.6% | 0.57 | 85.7% | 1 |

- **Adopted `COVERAGE_WEIGHTS_CROSSLINGUAL = 0.60 / 0.25 / 0.15`** — best exact
  accuracy and MAE, +14pts exact and +14pts answerable-recall over the
  monolingual blend, with no increase in worst-case flips.
- **Why it works:** in cross-lingual mode `term_overlap` runs on concept groups
  (term + its glossary translation), so it is the *explicitly bridged*, bounded
  signal. BM25/TF-IDF run on the expanded query and proved noisier — confirming
  the earlier observation that adding bridge terms moved some questions the wrong
  way. Demoting them helps.
- **Not overlap-only:** pure overlap maximizes recall (85.7%) but over-promotes
  true-Missing items (precision drops), so exact accuracy falls to 47.6%.

Only the cross-lingual, no-embedding path changed. Monolingual blends
(`COVERAGE_WEIGHTS`) and the embedding paths are untouched; all 44 tests pass.

## Update — embeddings ON by default (multilingual)

Local embeddings (sentence-transformers, `paraphrase-multilingual-MiniLM-L12-v2`)
are now the default. The model bridges languages semantically (EN "What is SEO?"
vs TH "SEO คือ…" cosine ≈ 0.84 vs ≈ -0.06 for an unrelated sentence), which the
glossary alone can't do. With embeddings on, the cross-lingual blend
(`COVERAGE_WEIGHTS_CROSSLINGUAL_EMB`) combines BOTH validated signals — they're
complementary (overlap = exact entity/keyword bridge, embeddings = paraphrase/
semantics). Re-swept on the same 21 judgments:

| Blend (overlap/tfidf/bm25/emb) | Exact | MAE | Answerable recall |
|---|---:|---:|---:|
| emb-heavy 0.15/0.10/0.10/0.65 (old guess) | 52.4% | 0.57 | 78.6% |
| 0.30/0.10/0.10/0.50 | 61.9% | 0.48 | 78.6% |
| **0.40/0.10/0.05/0.45 (adopted)** | **66.7%** | **0.43** | **85.7%** |
| 0.45/0.10/0.05/0.40 | 66.7% | 0.43 | 85.7% |

**Best overall = embeddings + overlap together (67% exact / 86% recall)** — better
than embeddings-heavy alone, pure-lexical overlap-B (57%), or the original default
(43%). The embedding-heavy 0.65 blend was a guess; combining the two signals is
the data-backed choice.

Reproduce the embedding sweep: `AISO_USE_EMBEDDINGS=1 python -m evals.run_crosslingual_eval`.

## Update 2 — threshold experiment: no change warranted

The earlier note flagged the Covered/Partial threshold (0.55 / 0.40, calibrated
monolingual) as the likely next lever, since *deterministic* cross-lingual scores
clustered low (true-Covered items stuck at 0.44–0.53). Since thresholds apply
*after* scoring, scores were computed once and re-classified across a grid
(`sweep_thresholds()` in the harness).

**Embeddings ON (default) — exact% / off-by-2:**

| cov \ par | 0.30 | 0.35 | 0.40 | 0.45 |
|---|---|---|---|---|
| 0.45 | 52/2 | 57/2 | 62/3 | — |
| 0.50 | 57/1 | 62/1 | **67/2** | **67/2** |
| 0.55 | 57/1 | 62/1 | **67/2 (current)** | **67/2** |
| 0.60 | 52/0 | 57/0 | 62/1 | 62/1 |

Exact accuracy sits on a **flat 67% plateau** across 0.50–0.55 covered ×
0.40–0.45 partial — the current 0.55/0.40 is already on it. **No threshold change
helps.** The reason: multilingual embeddings + the tuned blend lift true-Covered
items above 0.55, so the low-score clustering that motivated the hypothesis only
existed in the *deterministic* regime — embeddings fixed it upstream.

**Embeddings OFF (fallback):** a marginal +5pts (0.55/0.45 → 62%) exists, but it
raises worst-case Covered↔Missing flips (off-by-2: 2→3) and is the less-important
path now. Not a clean win → not adopted; no separate knob added.

**Decision: thresholds unchanged.** A documented negative result — the weight
tuning and default embeddings already solved the cross-lingual scoring problem,
and sliding thresholds on n=21 would be overfitting without benefit.

Reproduce: `AISO_USE_EMBEDDINGS=1 python -m evals.run_crosslingual_eval` (the
threshold sweep prints at the end).

## Honest caveats / next levers (not changed here)

1. **Small, subjective set (n=21).** Results are directional. The effect size and
   the mechanistic reason both point the same way, which is why it was adopted,
   but this is calibration on a sample, not a benchmark.
2. **The threshold is the next, possibly larger, lever.** Even the best blend
   tops out at 57% exact. Several *true-Covered* cross-lingual questions land at
   0.44–0.53 — just under the 0.55 Covered cutoff — because bridging is lossy and
   shifts the whole score distribution down. A cross-lingual-specific Covered
   threshold (~0.50) would likely recover several of these. Weights move scores;
   the threshold sets the boundary.
3. **Glossary/cue gaps.** A few misses (e.g. "getting started" / "process/steps"
   ↔ ขั้นตอน) are vocabulary the bridge doesn't cover yet, not a weighting issue.
4. **The real fix remains multilingual embeddings** — language-agnostic semantics
   that don't depend on glossary coverage. Lexical re-weighting is the best we can
   do deterministically; it is a patch, not the ceiling.

## Reproduce

```bash
python -m evals.run_crosslingual_eval
```
