"""Input validation for URLs, pasted content, and seed questions.

Validators never raise for user mistakes — they return structured results so
the UI and API can show friendly messages instead of stack traces.
"""

import re
from urllib.parse import urlparse

from src.config import MAX_CONTENT_CHARS, MAX_SEED_QUESTIONS


def validate_url(url: str) -> dict:
    """Return {ok, url, error}. Accepts http(s) URLs only; adds https:// if
    the user omitted a scheme."""
    url = (url or "").strip()
    if not url:
        return {"ok": False, "url": url, "error": "URL is empty."}
    if re.search(r"\s", url):
        return {"ok": False, "url": url, "error": "URL contains whitespace."}
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return {"ok": False, "url": url, "error": f"Unsupported scheme '{parsed.scheme}'. Use http or https."}
    if not parsed.netloc or "." not in parsed.netloc.split(":")[0]:
        if parsed.hostname not in ("localhost", "127.0.0.1"):
            return {"ok": False, "url": url, "error": "URL has no valid host."}
    if "@" in parsed.netloc:
        return {"ok": False, "url": url, "error": "URLs with embedded credentials are not supported."}
    return {"ok": True, "url": url, "error": None}


def validate_pasted_content(content: str) -> dict:
    """Return {ok, content, issues}. Truncates oversized pastes instead of failing."""
    issues = []
    content = content or ""
    if not content.strip():
        return {"ok": False, "content": "", "issues": ["Pasted content is empty."]}
    if len(content) > MAX_CONTENT_CHARS:
        issues.append(
            f"Content truncated to {MAX_CONTENT_CHARS:,} characters for analysis."
        )
        content = content[:MAX_CONTENT_CHARS]
    return {"ok": True, "content": content, "issues": issues}


def looks_like_html(content: str) -> bool:
    head = (content or "")[:4000].lower()
    return bool(re.search(r"<\s*(!doctype|html|head|body|div|p|h1|article|section|meta)\b", head))


def parse_seed_questions(raw: str) -> list:
    """One question per line; strips bullets/numbering, dedupes, caps length."""
    questions = []
    seen = set()
    for line in (raw or "").splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
        if not line or len(line) > 300:
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        questions.append(line)
        if len(questions) >= MAX_SEED_QUESTIONS:
            break
    return questions


def clean_short_field(value: str, max_len: int = 120) -> str:
    """For topic / audience style inputs."""
    return re.sub(r"\s+", " ", (value or "")).strip()[:max_len]
