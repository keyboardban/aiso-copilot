"""Retrieval-based content coverage: can this page answer each fan-out question?

Per question, three deterministic signals are blended (see SCORING_RUBRIC.md):

  - term_overlap : fraction of the question's content-bearing terms present in
                   the best-matching chunks (absolute evidence signal)
  - tfidf        : cosine similarity of the best chunk (0..1)
  - bm25         : saturated BM25 of the best chunk, s/(s+K) (0..1)

Optional local embeddings join the blend only when explicitly enabled. The
blended 0..1 score is classified Covered / Partial / Missing by thresholds.
No LLM is involved anywhere in coverage scoring.
"""

import re

from src.config import (
    BM25_SATURATION_K,
    COVERAGE_WEIGHTS,
    COVERAGE_WEIGHTS_CROSSLINGUAL,
    COVERAGE_WEIGHTS_CROSSLINGUAL_EMB,
    COVERAGE_WEIGHTS_EMB,
    COVERED_THRESHOLD,
    PARTIAL_THRESHOLD,
    TOP_K_EVIDENCE,
)
from src.query.bilingual import bridge_terms, equivalents, intent_cues
from src.retrieval.bm25_retriever import BM25Retriever
from src.retrieval.embedding_retriever import EmbeddingRetriever
from src.retrieval.tfidf_retriever import TfidfRetriever
from src.utils.text import (
    STOPWORDS_EN,
    THAI_STOP_SUBSTRINGS,
    THAI_TOKENIZER,
    contains_thai,
    tokenize,
    truncate,
)

# A page is treated as Thai-dominant when at least this fraction of its chunks
# contain Thai script; cross-lingual handling triggers when the question's
# language differs from this.
_THAI_CORPUS_RATIO = 0.30

_RECOMMENDATION_BY_INTENT = {
    "definition": "Add a concise 2–3 sentence definition that answers this directly, ideally under a question-style heading near the top of the page.",
    "comparison": "Add a short comparison section (or table) that names both options and states the concrete differences.",
    "implementation": "Add a step-by-step section that walks through how to do this, with one clear action per step.",
    "measurement": "Add a section naming the specific metrics, tools, and review cadence you use to measure this.",
    "commercial": "Add a passage that addresses the buying question directly: who it is for, what it includes, and what determines effort or cost.",
    "technical": "Add a technically specific passage (tools, data, requirements) so systems can quote concrete facts.",
    "trust": "Add verifiable trust evidence: who you are, credentials, named results, or external references that support the claim.",
    "local": "Add market-specific content: name the location, the local audience, and locally relevant examples.",
    "schema": "Explain the role of structured data explicitly in the visible text, and back it with matching JSON-LD markup.",
    "proof": "Add at least one concrete proof point: a case study, named client outcome, or measurable result.",
    "content_strategy": "Add a passage describing the content structure or strategy explicitly, with examples of what good looks like.",
}

_THAI_RUN_RE = re.compile(r"[\u0e00-\u0e7f]+")
_LATIN_RE = re.compile(r"[a-z0-9][a-z0-9'\-]*")


def _display_terms(question: str) -> list:
    """Human-readable content terms of a question: Latin words plus Thai content
    terms, used for the overlap signal and gap explanations.

    With newmm, Thai terms are real words (cleanly displayable as missing
    terms); with the trigram fallback they are coarse stop-particle-split
    segments, matching the tokenizer's notion of a Thai unit in each mode.
    """
    text = (question or "").lower()
    terms = [t for t in _LATIN_RE.findall(text) if t not in STOPWORDS_EN]
    if THAI_TOKENIZER == "newmm":
        # real Thai words from the tokenizer (drop very short particles)
        terms += [t for t in tokenize(text, remove_stopwords=True)
                  if _THAI_RUN_RE.match(t) and len(t) >= 2]
    else:
        for run in _THAI_RUN_RE.findall(text):
            for stop in THAI_STOP_SUBSTRINGS:
                run = run.replace(stop, " ")
            terms.extend(part for part in run.split() if len(part) >= 3)
    seen, unique = set(), []
    for term in terms:
        if term not in seen:
            seen.add(term)
            unique.append(term)
    return unique


# Short Latin acronyms that should still get substring matching despite length.
_ACRONYM_WHITELIST = {"seo", "geo", "aeo", "ppc", "gpt", "llm", "cro", "sem"}


def _term_present(term: str, token_set: set) -> bool:
    if _THAI_RUN_RE.match(term):
        if THAI_TOKENIZER == "newmm":
            # query terms and chunk tokens are segmented the same way → exact match
            return term in token_set
        grams = [term[i : i + 3] for i in range(max(1, len(term) - 2))]
        hits = sum(1 for g in grams if g in token_set)
        return hits / len(grams) >= 0.5
    if term in token_set:
        return True
    # Check 3 fallback: the HTML extractor can still emit mashed tokens
    # (e.g. "seoservices"). For meaningful Latin terms, accept a substring hit
    # inside a clearly-longer token. Guards (length, whitelist, size gap) keep
    # false positives like "ai" in "maintain" out.
    if len(term) >= 4 or term in _ACRONYM_WHITELIST:
        for tok in token_set:
            if len(tok) >= len(term) + 2 and term in tok:
                return True
    return False


def _concept_groups(display_terms: list, intent: str, cross_lingual: bool,
                    page_is_thai: bool) -> list:
    """Build overlap groups as ``(anchor, members)`` pairs.

    Monolingual: one group per term, ``members={term}`` → behaves exactly like
    the old flat overlap. Cross-lingual: each term's group also includes its
    cross-language equivalents, plus one extra anchorless group of the page-
    language intent cues, so a page answering the intent in its own words counts.
    """
    groups = []
    for term in display_terms:
        members = {term}
        if cross_lingual:
            members.update(equivalents(term))
        groups.append((term, members))
    if cross_lingual:
        cues = intent_cues(intent, want_thai=page_is_thai)
        if cues:
            groups.append((None, set(cues)))
    return groups


def evaluate_coverage(chunks: list, questions: list, llm=None) -> dict:
    """Return {"coverage_matrix": [...], "coverage_score": int, "method": str}.

    ``questions`` is a list of {"question", "intent", "source"} dicts.
    """
    matrix = []
    if not questions:
        return {"coverage_matrix": [], "coverage_score": 0, "method": "none"}

    bm25 = BM25Retriever(chunks)
    tfidf = TfidfRetriever(chunks)
    embeddings = EmbeddingRetriever(chunks)

    base_method = f"bm25({bm25.backend}) + tfidf({tfidf.backend}) + term_overlap"
    if embeddings.available:
        base_method += f" + embeddings({embeddings.model_name.split('/')[-1]})"

    chunk_token_sets = [set(tokenize(c["text"])) for c in chunks]

    # Detect the page's dominant language once, to decide per-question whether a
    # question is cross-lingual to the content (Checks 1 & 4).
    thai_chunks = sum(1 for c in chunks if contains_thai(c.get("text", "")))
    page_is_thai = bool(chunks) and (thai_chunks / len(chunks)) >= _THAI_CORPUS_RATIO
    crosslingual_used = False

    for item in questions:
        question = item["question"]
        intent = item.get("intent", "definition")
        source = item.get("source", "template")

        if not chunks:
            matrix.append(
                {
                    "question": question,
                    "intent": intent,
                    "source": source,
                    "coverage": "Missing",
                    "score": 0.0,
                    "evidence": [],
                    "gap": "No extractable content to retrieve from.",
                    "recommendation": _RECOMMENDATION_BY_INTENT.get(intent, ""),
                }
            )
            continue

        # Cross-lingual when the question's language differs from the page's.
        question_is_thai = contains_thai(question)
        cross_lingual = bool(chunks) and (question_is_thai != page_is_thai)
        if cross_lingual:
            crosslingual_used = True

        display_terms = _display_terms(question)
        groups = _concept_groups(display_terms, intent, cross_lingual, page_is_thai)

        # Check 1: expand the lexical retrieval query toward the PAGE language so
        # BM25/TF-IDF can find relevant chunks written in the other language.
        if cross_lingual:
            extra = bridge_terms(display_terms, intent, target_is_thai=page_is_thai)
            retrieval_query = (question + " " + " ".join(extra)).strip() if extra else question
        else:
            retrieval_query = question

        bm25_scores = bm25.score_all(retrieval_query)
        tfidf_scores = tfidf.score_all(retrieval_query)
        # embeddings score on the ORIGINAL question — a multilingual model bridges
        # languages semantically without query expansion (Check 4).
        emb_scores = embeddings.score_all(question) if embeddings.available else []

        # Choose the blend. Cross-lingual + embeddings → lean semantic (Check 4);
        # cross-lingual without embeddings → COVERAGE_WEIGHTS_CROSSLINGUAL knob
        # (the eval harness tunes this); else the monolingual default.
        if cross_lingual and emb_scores:
            weights = COVERAGE_WEIGHTS_CROSSLINGUAL_EMB
        elif emb_scores:
            weights = COVERAGE_WEIGHTS_EMB
        elif cross_lingual:
            weights = COVERAGE_WEIGHTS_CROSSLINGUAL
        else:
            weights = COVERAGE_WEIGHTS

        blended = []
        for i in range(len(chunks)):
            token_set = chunk_token_sets[i]
            if groups:
                covered_groups = sum(
                    1 for _, members in groups
                    if any(_term_present(m, token_set) for m in members)
                )
                overlap = covered_groups / len(groups)
            else:
                overlap = 0.0
            bm25_sat = bm25_scores[i] / (bm25_scores[i] + BM25_SATURATION_K) if bm25_scores else 0.0
            tfidf_cos = tfidf_scores[i] if tfidf_scores else 0.0
            score = (
                weights["term_overlap"] * overlap
                + weights["tfidf"] * tfidf_cos
                + weights["bm25"] * bm25_sat
            )
            if emb_scores:
                score += weights["embeddings"] * emb_scores[i]
            elif not groups:
                # question had no content terms: renormalize without overlap
                denominator = 1.0 - weights["term_overlap"]
                score = score / denominator if denominator else score
            blended.append(score)

        order = sorted(range(len(chunks)), key=lambda i: blended[i], reverse=True)
        best_score = blended[order[0]] if order else 0.0
        top_idx = [i for i in order[:TOP_K_EVIDENCE] if blended[i] >= 0.15]

        if best_score >= COVERED_THRESHOLD:
            coverage = "Covered"
        elif best_score >= PARTIAL_THRESHOLD:
            coverage = "Partial"
        else:
            coverage = "Missing"

        evidence = [
            {
                "section": chunks[i]["section"],
                "text": truncate(chunks[i]["text"], 300),
                "score": round(blended[i], 3),
            }
            for i in top_idx
        ]

        gap = None
        recommendation = None
        if coverage != "Covered":
            evidence_tokens = set()
            for i in top_idx:
                evidence_tokens |= chunk_token_sets[i]
            # a term is "addressed" if it or any cross-language equivalent appears
            missing_terms = [
                anchor for anchor, members in groups
                if anchor and not any(_term_present(m, evidence_tokens) for m in members)
            ]
            if coverage == "Missing":
                gap = "The page has little or no evidence for this question."
            else:
                gap = "Some related evidence exists but the question is not answered completely."
            if missing_terms:
                gap += " Not addressed: " + ", ".join(missing_terms[:6]) + "."
            recommendation = _RECOMMENDATION_BY_INTENT.get(intent, "Add a passage that answers this question directly.")

        matrix.append(
            {
                "question": question,
                "intent": intent,
                "source": source,
                "coverage": coverage,
                "score": round(best_score, 3),
                "evidence": evidence,
                "gap": gap,
                "recommendation": recommendation,
            }
        )

    covered = sum(1 for row in matrix if row["coverage"] == "Covered")
    partial = sum(1 for row in matrix if row["coverage"] == "Partial")
    coverage_score = round(100 * (covered + 0.5 * partial) / len(matrix)) if matrix else 0

    method = base_method
    if crosslingual_used:
        method += " + cross-lingual bridge"
        if not embeddings.available:
            method += " (enable AISO_USE_EMBEDDINGS with a multilingual model for best cross-lingual recall)"

    return {"coverage_matrix": matrix, "coverage_score": coverage_score, "method": method}
