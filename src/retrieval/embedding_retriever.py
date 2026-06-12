"""Optional local embedding retrieval (sentence-transformers).

Strictly opt-in: requires `pip install -r requirements-local.txt` AND
AISO_USE_EMBEDDINGS=1. When unavailable for any reason, `available` stays
False and hybrid coverage simply runs without the embedding signal. No paid
embedding API is ever used.
"""

from src.config import EMBEDDING_MODEL_NAME, USE_EMBEDDINGS


class EmbeddingRetriever:
    def __init__(self, chunks: list):
        self.chunks = chunks
        self.available = False
        self._model = None
        self._matrix = None
        if not USE_EMBEDDINGS or not chunks:
            return
        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np

            self._np = np
            self._model = SentenceTransformer(EMBEDDING_MODEL_NAME)
            texts = [c["text"] for c in chunks]
            matrix = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            self._matrix = np.asarray(matrix)
            self.available = True
        except Exception:
            # model missing, no disk space, no internet for first download, etc.
            self.available = False

    def score_all(self, query: str) -> list:
        """Cosine similarity (0..1) for every chunk; [] when unavailable."""
        if not self.available:
            return []
        try:
            query_vec = self._model.encode([query], normalize_embeddings=True, show_progress_bar=False)
            sims = (self._matrix @ self._np.asarray(query_vec).T).ravel()
            return [max(0.0, min(1.0, float(s))) for s in sims]
        except Exception:
            return []
