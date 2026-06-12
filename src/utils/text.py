"""Shared text utilities: tokenization, stopwords, sentence splitting.

Tokenization is the backbone of all deterministic retrieval in AISO Copilot, so
it lives in one place. Thai text has no spaces between words; rather than pull
in a heavyweight segmenter, Thai runs are tokenized into character trigrams,
which is a cheap, dependency-free approximation that lets Thai queries match
Thai passages well enough for coverage classification.
"""

import re
import unicodedata

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


def tokenize(text: str, remove_stopwords: bool = False) -> list:
    """Tokenize mixed Thai/English text.

    Latin words become lowercase word tokens; Thai runs become character
    trigrams. With ``remove_stopwords=True``, English stopwords are dropped and
    common Thai function words are stripped before trigramming.
    """
    if not text:
        return []
    text = unicodedata.normalize("NFC", text).lower()
    tokens = []
    for match in _TOKEN_RE.finditer(text):
        token = match.group(0)
        if _THAI_RE.match(token):
            run = token
            if remove_stopwords:
                for stop in THAI_STOP_SUBSTRINGS:
                    run = run.replace(stop, " ")
            for part in run.split():
                tokens.extend(_thai_ngrams(part))
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
