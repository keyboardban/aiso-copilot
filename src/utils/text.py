"""Shared text utilities: tokenization, stopwords, sentence splitting.

Tokenization is the backbone of all deterministic retrieval in AISO Copilot, so
it lives in one place. Thai text has no spaces between words. Two strategies are
supported, selected automatically at import time:

  * ``newmm``  \u2014 PyThaiNLP's dictionary-based word segmenter (preferred). Real
    Thai words make retrieval, gap explanations, and stopword removal cleaner.
    Optional dependency (``pip install -r requirements-local.txt``).
  * ``trigram`` \u2014 character-trigram fallback used when PyThaiNLP is not
    installed. Dependency-free; matches Thai queries against Thai passages well
    enough for coverage classification without any word segmentation.

The active strategy is exposed as ``THAI_TOKENIZER`` so callers that need to
reason about Thai terms (e.g. coverage matching) can branch accordingly.
"""

import re
import unicodedata

try:  # optional: PyThaiNLP word segmentation (see requirements-local.txt)
    from pythainlp.corpus import thai_stopwords as _pythai_stopwords
    from pythainlp.tokenize import word_tokenize as _pythai_word_tokenize

    _HAS_PYTHAINLP = True
    THAI_TOKENIZER = "newmm"
    _THAI_STOPWORDS = set(_pythai_stopwords())
except Exception:  # pragma: no cover - exercised only when pythainlp is absent
    _HAS_PYTHAINLP = False
    THAI_TOKENIZER = "trigram"
    _THAI_STOPWORDS = set()

# Latin/digit words (keeps hyphens and apostrophes inside words) OR Thai runs.
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9'\-]*|[\u0e00-\u0e7f]+")
_THAI_RE = re.compile(r"[\u0e00-\u0e7f]")

STOPWORDS_EN = {
    "a", "an", "and", "are", "as", "at", "be", "best", "by", "can", "do", "does",
    "for", "from", "get", "has", "have", "how", "i", "if", "in", "into", "is",
    "it", "its", "more", "most", "much", "my", "need", "needs", "of", "on", "or",
    "our", "should", "so", "than", "that", "the", "their", "them", "there",
    "these", "they", "this", "to", "use", "used", "we", "what", "when", "where",
    "which", "who", "why", "will", "with", "you", "your",
}

# Common Thai function words / question particles, removed (as substrings)
# before trigramming when stopword removal is requested. Heuristic by design.
THAI_STOP_SUBSTRINGS = [
    "คืออะไร", "อย่างไร", "ทำไม", "อะไร", "ที่", "ของ", "และ", "ใน", "ให้",
    "ได้", "เป็น", "คือ", "กับ", "ว่า", "จะ", "ๆ", "ถึง", "ควร",
]


def normalize_ws(text: str) -> str:
    """Collapse whitespace runs into single spaces."""
    return re.sub(r"\s+", " ", text or "").strip()


def contains_thai(text: str) -> bool:
    return bool(_THAI_RE.search(text or ""))


def _thai_ngrams(run: str, n: int = 3) -> list:
    if len(run) <= n:
        return [run] if run else []
    return [run[i : i + n] for i in range(len(run) - n + 1)]


def _thai_tokens(run: str, remove_stopwords: bool = False) -> list:
    """Tokenize one Thai run. Uses PyThaiNLP ``newmm`` word segmentation when
    available, else falls back to character trigrams. Both paths optionally
    drop Thai stopwords (real words for newmm; substring particles for trigram).
    """
    if _HAS_PYTHAINLP:
        words = _pythai_word_tokenize(run, engine="newmm", keep_whitespace=False)
        out = []
        for word in words:
            word = word.strip()
            if not word or not _THAI_RE.search(word):  # drop stray punctuation
                continue
            if remove_stopwords and word in _THAI_STOPWORDS:
                continue
            out.append(word)
        return out

    # trigram fallback (dependency-free)
    if remove_stopwords:
        for stop in THAI_STOP_SUBSTRINGS:
            run = run.replace(stop, " ")
    tokens = []
    for part in run.split():
        tokens.extend(_thai_ngrams(part))
    return tokens


def tokenize(text: str, remove_stopwords: bool = False) -> list:
    """Tokenize mixed Thai/English text.

    Latin words become lowercase word tokens; Thai runs become either real
    words (PyThaiNLP ``newmm``) or character trigrams (fallback), per
    ``THAI_TOKENIZER``. With ``remove_stopwords=True``, English and Thai
    stopwords are dropped.
    """
    if not text:
        return []
    text = unicodedata.normalize("NFC", text).lower()
    tokens = []
    for match in _TOKEN_RE.finditer(text):
        token = match.group(0)
        if _THAI_RE.match(token):
            tokens.extend(_thai_tokens(token, remove_stopwords))
        else:
            if remove_stopwords and token in STOPWORDS_EN:
                continue
            tokens.append(token)
    return tokens


def content_terms(text: str) -> set:
    """Unique evidence-bearing terms of a query (stopwords removed)."""
    return set(tokenize(text, remove_stopwords=True))


def split_sentences(text: str) -> list:
    """Light sentence splitter. Thai text without punctuation stays as one
    sentence per paragraph line — a documented limitation, fine for snippets."""
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [normalize_ws(p) for p in parts if normalize_ws(p)]


def word_count(text: str) -> int:
    """Word count that approximates Thai words as ~4 characters each."""
    if not text:
        return 0
    latin = re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]*", text)
    thai_runs = re.findall(r"[\u0e00-\u0e7f]+", text)
    thai_words = sum(max(1, round(len(run) / 4)) for run in thai_runs)
    return len(latin) + thai_words


def slugify(text: str, max_len: int = 60) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:max_len] or "untitled"


def truncate(text: str, max_chars: int = 280) -> str:
    text = normalize_ws(text)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rsplit(" ", 1)[0] + "…"
