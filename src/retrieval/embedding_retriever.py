"""Local embedding retrieval (sentence-transformers).

ON by default (AISO_USE_EMBEDDINGS=1) with a multilingual model, so cross-lingual
semantic matching works out of the box. Degrades gracefully: if
sentence-transformers isn't installed, or the model can't load (e.g. offline on
first run), ``available`` stays False and hybrid coverage runs on the
deterministic lexical signals only. No paid embedding API is ever used.

The model is loaded once per process and cached (keyed by model name), so
repeated audits don't reload it from disk.
"""

from src.config import EMBEDDING_MODEL_NAME, USE_EMBEDDINGS

# process-wide cache: {model_name: (model, numpy_module)} or {model_name: None}
# (None records a failed load so we don't retry a broken model every analysis).
_MODEL_CACHE = {}


def _load_model(name: str):
    """Return (model, numpy) for ``name``, loading once and caching. Returns
    (None, None) if unavailable for any reason."""
    if name in _MODEL_CACHE:
        return _MODEL_CACHE[name]
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np

        model = SentenceTransformer(name)
        _MODEL_CACHE[name] = (model, np)
    except Exception:
        # not installed, no disk space, no internet for first download, etc.
        _MODEL_CACHE[name] = (None, None)
    return _MODEL_CACHE[name]


def embeddings_backend() -> str:
    """Best-effort name of the active embedding model, or '' if unavailable."""
    if not USE_EMBEDDINGS:
        return ""
    model, _ = _load_model(EMBEDDING_MODEL_NAME)
    return EMBEDDING_MODEL_NAME if model is not None else ""


class EmbeddingRetriever:
    def __init__(self, chunks: list):
        self.chunks = chunks
        self.available = False
        self._model = None
        self._np = None
        self._matrix = None
        self.model_name = EMBEDDING_MODEL_NAME
        if not USE_EMBEDDINGS or not chunks:
            return
        model, np = _load_model(EMBEDDING_MODEL_NAME)
        if model is None:
            return
        try:
            texts = [c["text"] for c in chunks]
            matrix = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            self._model = model
            self._np = np
            self._matrix = np.asarray(matrix)
            self.available = True
        except Exception:
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
