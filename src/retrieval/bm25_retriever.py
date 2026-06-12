"""BM25 retrieval over page chunks.

Uses rank-bm25 when installed; otherwise falls back to a built-in Okapi BM25
implementation so the analyzer keeps working on a minimal Python install.
Scores are raw BM25 (unbounded); hybrid_coverage saturates them to 0..1.
"""

import math

from src.utils.text import tokenize

try:
    from rank_bm25 import BM25Okapi

    _HAS_RANK_BM25 = True
except ImportError:
    _HAS_RANK_BM25 = False


class _PurePythonBM25:
    """Minimal Okapi BM25 (k1=1.5, b=0.75) matching rank_bm25 semantics."""

    def __init__(self, corpus_tokens: list, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus = corpus_tokens
        self.doc_lens = [len(doc) for doc in corpus_tokens]
        self.avgdl = (sum(self.doc_lens) / len(self.doc_lens)) if corpus_tokens else 0.0
        self.doc_freqs = []
        df = {}
        for doc in corpus_tokens:
            freqs = {}
            for token in doc:
                freqs[token] = freqs.get(token, 0) + 1
            self.doc_freqs.append(freqs)
            for token in freqs:
                df[token] = df.get(token, 0) + 1
        n = len(corpus_tokens)
        self.idf = {
            token: math.log((n - freq + 0.5) / (freq + 0.5) + 1.0)
            for token, freq in df.items()
        }

    def get_scores(self, query_tokens: list) -> list:
        scores = [0.0] * len(self.corpus)
        for token in query_tokens:
            idf = self.idf.get(token)
            if idf is None:
                continue
            for i, freqs in enumerate(self.doc_freqs):
                tf = freqs.get(token, 0)
                if not tf:
                    continue
                denom = tf + self.k1 * (1 - self.b + self.b * self.doc_lens[i] / (self.avgdl or 1))
                scores[i] += idf * tf * (self.k1 + 1) / denom
        return scores


class BM25Retriever:
    def __init__(self, chunks: list):
        self.chunks = chunks
        self.tokenized = [tokenize(c["text"]) for c in chunks]
        self.backend = "none"
        self._bm25 = None
        if not chunks:
            return
        usable = [t if t else ["<empty>"] for t in self.tokenized]
        if _HAS_RANK_BM25:
            self._bm25 = BM25Okapi(usable)
            self.backend = "rank_bm25"
        else:
            self._bm25 = _PurePythonBM25(usable)
            self.backend = "pure_python"

    def score_all(self, query: str) -> list:
        """Raw BM25 score for every chunk (parallel to ``chunks``)."""
        if not self._bm25:
            return []
        query_tokens = tokenize(query)
        if not query_tokens:
            return [0.0] * len(self.chunks)
        scores = self._bm25.get_scores(query_tokens)
        return [max(0.0, float(s)) for s in scores]

    def top_k(self, query: str, k: int = 5) -> list:
        scores = self.score_all(query)
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [(i, scores[i]) for i in order[:k] if scores[i] > 0]
