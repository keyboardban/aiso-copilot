"""TF-IDF cosine similarity retrieval over page chunks.

Uses scikit-learn when installed (with the project's Thai-aware tokenizer as
the analyzer); otherwise falls back to a small pure-Python TF-IDF so retrieval
never becomes a hard dependency problem. Scores are cosine similarity in 0..1.
"""

import math

from src.utils.text import tokenize

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import linear_kernel

    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False


class _PurePythonTfidf:
    def __init__(self, corpus_tokens: list):
        self.n = len(corpus_tokens)
        df = {}
        for doc in corpus_tokens:
            for token in set(doc):
                df[token] = df.get(token, 0) + 1
        # smooth idf, matching sklearn's default formulation
        self.idf = {t: math.log((1 + self.n) / (1 + f)) + 1.0 for t, f in df.items()}
        self.vectors = [self._vectorize(doc) for doc in corpus_tokens]

    def _vectorize(self, tokens: list) -> dict:
        tf = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1
        vec = {t: c * self.idf.get(t, math.log(1 + self.n) + 1.0) for t, c in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}

    def similarities(self, query_tokens: list) -> list:
        query_vec = self._vectorize(query_tokens)
        sims = []
        for vec in self.vectors:
            small, large = (query_vec, vec) if len(query_vec) < len(vec) else (vec, query_vec)
            sims.append(sum(v * large.get(t, 0.0) for t, v in small.items()))
        return sims


class TfidfRetriever:
    def __init__(self, chunks: list):
        self.chunks = chunks
        self.backend = "none"
        self._vectorizer = None
        self._matrix = None
        self._fallback = None
        if not chunks:
            return
        texts = [c["text"] for c in chunks]
        if _HAS_SKLEARN:
            try:
                self._vectorizer = TfidfVectorizer(analyzer=tokenize)
                self._matrix = self._vectorizer.fit_transform(texts)
                self.backend = "sklearn"
                return
            except ValueError:  # e.g. empty vocabulary
                self._vectorizer = None
        self._fallback = _PurePythonTfidf([tokenize(t) for t in texts])
        self.backend = "pure_python"

    def score_all(self, query: str) -> list:
        """Cosine similarity (0..1) for every chunk (parallel to ``chunks``)."""
        if not self.chunks:
            return []
        if self._vectorizer is not None:
            query_vec = self._vectorizer.transform([query])
            sims = linear_kernel(query_vec, self._matrix)[0]
            return [max(0.0, min(1.0, float(s))) for s in sims]
        if self._fallback is not None:
            sims = self._fallback.similarities(tokenize(query))
            return [max(0.0, min(1.0, s)) for s in sims]
        return [0.0] * len(self.chunks)

    def top_k(self, query: str, k: int = 5) -> list:
        scores = self.score_all(query)
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [(i, scores[i]) for i in order[:k] if scores[i] > 0]
