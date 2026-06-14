"""Cross-lingual coverage weight sweep.

Answers: "should the deterministic blend re-weight for bilingual mismatch?"
Runs the labeled dataset through several candidate COVERAGE_WEIGHTS_CROSSLINGUAL
blends and reports classification quality, so the choice is data-driven.

Run:  python -m evals.run_crosslingual_eval

Metrics per blend:
  - exact      : exact 3-class accuracy (Covered/Partial/Missing)
  - ordinal MAE: mean |pred-expected| with Missing=0, Partial=1, Covered=2
  - answerable recall: of questions labeled Covered/Partial, fraction NOT
                       predicted Missing (directly measures the cross-lingual
                       "everything goes Missing" failure)
  - off-by-2   : count of Covered<->Missing flips (the worst errors)
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import src.retrieval.hybrid_coverage as hc
from evals.crosslingual_dataset import all_cases, label_counts
from src.crawler.extract_content import extract_content
from src.retrieval.chunker import build_chunks

ORD = {"Missing": 0, "Partial": 1, "Covered": 2}

CANDIDATES = {
    "current (0.40/0.35/0.25)": {"term_overlap": 0.40, "tfidf": 0.35, "bm25": 0.25},
    "overlap-A (0.55/0.25/0.20)": {"term_overlap": 0.55, "tfidf": 0.25, "bm25": 0.20},
    "overlap-B (0.60/0.25/0.15)": {"term_overlap": 0.60, "tfidf": 0.25, "bm25": 0.15},
    "overlap-heavy (0.70/0.20/0.10)": {"term_overlap": 0.70, "tfidf": 0.20, "bm25": 0.10},
    "overlap-only (1.0/0/0)": {"term_overlap": 1.0, "tfidf": 0.0, "bm25": 0.0},
}

# Embedding-on cross-lingual blends (only swept when sentence-transformers is
# available — i.e. run with AISO_USE_EMBEDDINGS=1).
EMB_CANDIDATES = {
    "emb-heavy o.15/t.10/b.10/e.65": {"term_overlap": 0.15, "tfidf": 0.10, "bm25": 0.10, "embeddings": 0.65},
    "emb+overlap o.30/t.10/b.10/e.50": {"term_overlap": 0.30, "tfidf": 0.10, "bm25": 0.10, "embeddings": 0.50},
    "balanced o.40/t.10/b.05/e.45 (adopted)": {"term_overlap": 0.40, "tfidf": 0.10, "bm25": 0.05, "embeddings": 0.45},
    "overlap-lead o.45/t.10/b.05/e.40": {"term_overlap": 0.45, "tfidf": 0.10, "bm25": 0.05, "embeddings": 0.40},
}


def _predict(page_html, questions, weights):
    page = extract_content(page_html, "html")
    chunks = build_chunks(page)
    items = [{"question": q, "intent": i, "source": "eval"} for q, i, _ in questions]
    hc.COVERAGE_WEIGHTS_CROSSLINGUAL = weights  # module global → read at call time
    result = hc.evaluate_coverage(chunks, items)
    return result["coverage_matrix"]


def _score(weights):
    rows = []
    for _, page_html, questions in all_cases():
        matrix = _predict(page_html, questions, weights)
        for (q, intent, expected), pred in zip(questions, matrix):
            rows.append((expected, pred["coverage"], pred["score"]))

    n = len(rows)
    exact = sum(1 for e, p, _ in rows if e == p) / n
    mae = sum(abs(ORD[e] - ORD[p]) for e, p, _ in rows) / n
    answerable = [(e, p) for e, p, _ in rows if e in ("Covered", "Partial")]
    ans_recall = sum(1 for e, p in answerable if p != "Missing") / len(answerable)
    off2 = sum(1 for e, p, _ in rows if abs(ORD[e] - ORD[p]) == 2)
    return {"exact": exact, "mae": mae, "ans_recall": ans_recall, "off2": off2, "rows": rows}


def main():
    print("Cross-lingual weight sweep (deterministic / no embeddings)")
    print("Dataset label distribution:", label_counts())
    print(f"Total judgments: {sum(label_counts().values())}\n")

    header = f"{'blend':<32}{'exact':>8}{'MAE':>8}{'answ.recall':>13}{'off-by-2':>10}"
    print(header)
    print("-" * len(header))
    results = {}
    for name, weights in CANDIDATES.items():
        s = _score(weights)
        results[name] = s
        print(f"{name:<32}{s['exact']*100:>7.1f}%{s['mae']:>8.2f}"
              f"{s['ans_recall']*100:>12.1f}%{s['off2']:>10}")

    # detail for the current blend vs the best-by-exact, to see what moved
    best = max(results, key=lambda k: (results[k]["exact"], results[k]["ans_recall"], -results[k]["mae"]))
    print(f"\nBest by (exact, answerable-recall, -MAE): {best}")

    print("\nPer-question: expected -> [current] / [best]")
    cur = results["current (0.40/0.35/0.25)"]["rows"]
    bst = results[best]["rows"]
    qs = [q for _, _, questions in all_cases() for q, _, _ in questions]
    for q, (e, pc, sc), (_, pb, sb) in zip(qs, cur, bst):
        flag = "" if pc == pb else "   <-- changed"
        print(f"  {e:<8} -> {pc:<8}({sc:.2f}) / {pb:<8}({sb:.2f})  {q[:46]}{flag}")

    # embedding-on sweep (only meaningful when embeddings are actually available)
    from src.retrieval.embedding_retriever import embeddings_backend

    if embeddings_backend():
        print(f"\nEmbedding-on sweep (model: {embeddings_backend().split('/')[-1]}):")
        print(header)
        print("-" * len(header))
        original = hc.COVERAGE_WEIGHTS_CROSSLINGUAL_EMB
        for name, weights in EMB_CANDIDATES.items():
            hc.COVERAGE_WEIGHTS_CROSSLINGUAL_EMB = weights
            s = _score_emb()
            print(f"{name:<32}{s['exact']*100:>7.1f}%{s['mae']:>8.2f}"
                  f"{s['ans_recall']*100:>12.1f}%{s['off2']:>10}")
        hc.COVERAGE_WEIGHTS_CROSSLINGUAL_EMB = original
    else:
        print("\n(Embedding-on sweep skipped — run with AISO_USE_EMBEDDINGS=1 and "
              "sentence-transformers installed to include it.)")

    sweep_thresholds()


def sweep_thresholds():
    """Sweep Covered/Partial cutoffs on the LIVE default config (current blend +
    whatever embedding state the env is in). Thresholds apply after scoring, so
    scores are computed once and re-classified — isolating the threshold effect.
    """
    from src.config import COVERED_THRESHOLD, PARTIAL_THRESHOLD

    # collect (expected, best_score) once
    data = []
    for _, page_html, questions in all_cases():
        page = extract_content(page_html, "html")
        chunks = build_chunks(page)
        items = [{"question": q, "intent": i, "source": "eval"} for q, i, _ in questions]
        matrix = hc.evaluate_coverage(chunks, items)["coverage_matrix"]
        for (q, intent, expected), pred in zip(questions, matrix):
            data.append((expected, pred["score"]))

    def classify(s, cov, par):
        return "Covered" if s >= cov else ("Partial" if s >= par else "Missing")

    def metrics(cov, par):
        rows = [(e, classify(s, cov, par)) for e, s in data]
        n = len(rows)
        exact = sum(1 for e, p in rows if e == p) / n
        off2 = sum(1 for e, p in rows if abs(ORD[e] - ORD[p]) == 2)
        return exact, off2

    cur_exact, cur_off2 = metrics(COVERED_THRESHOLD, PARTIAL_THRESHOLD)
    print(f"\nThreshold sweep (current {COVERED_THRESHOLD}/{PARTIAL_THRESHOLD} → "
          f"exact {cur_exact*100:.1f}%, off-by-2 {cur_off2}). cell = exact% / off-by-2")
    pars = [0.30, 0.35, 0.40, 0.45]
    print(f"{'cov\\par':>8}" + "".join(f"{p:>10}" for p in pars))
    best = (cur_exact, -cur_off2, COVERED_THRESHOLD, PARTIAL_THRESHOLD)
    for cov in [0.45, 0.50, 0.55, 0.60]:
        cells = ""
        for par in pars:
            if par >= cov:
                cells += f"{'--':>10}"
                continue
            e, o = metrics(cov, par)
            cells += f"{e*100:>6.0f}/{o:<3}"
            if (e, -o) > (best[0], best[1]):
                best = (e, -o, cov, par)
        print(f"{cov:>8}{cells}")
    if (best[2], best[3]) == (COVERED_THRESHOLD, PARTIAL_THRESHOLD):
        print("→ current thresholds are already on the optimal plateau; no change warranted.")
    else:
        print(f"→ best: {best[2]}/{best[3]} (exact {best[0]*100:.1f}%, off-by-2 {-best[1]}) "
              "— adopt only if robust, not a single-cell spike.")


def _score_emb():
    """Score using the live evaluate_coverage (embeddings active); the lexical
    weights are ignored because the cross-lingual+embeddings path is used."""
    rows = []
    for _, page_html, questions in all_cases():
        page = extract_content(page_html, "html")
        chunks = build_chunks(page)
        items = [{"question": q, "intent": i, "source": "eval"} for q, i, _ in questions]
        matrix = hc.evaluate_coverage(chunks, items)["coverage_matrix"]
        for (q, intent, expected), pred in zip(questions, matrix):
            rows.append((expected, pred["coverage"], pred["score"]))
    n = len(rows)
    exact = sum(1 for e, p, _ in rows if e == p) / n
    mae = sum(abs(ORD[e] - ORD[p]) for e, p, _ in rows) / n
    answerable = [(e, p) for e, p, _ in rows if e in ("Covered", "Partial")]
    ans_recall = sum(1 for e, p in answerable if p != "Missing") / len(answerable)
    off2 = sum(1 for e, p, _ in rows if abs(ORD[e] - ORD[p]) == 2)
    return {"exact": exact, "mae": mae, "ans_recall": ans_recall, "off2": off2}


if __name__ == "__main__":
    main()
