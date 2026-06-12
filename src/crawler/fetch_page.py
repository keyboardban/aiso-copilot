"""Fetch a webpage over HTTP with friendly, structured failure modes.

URL mode is best-effort by design: many sites block bots or render via JS.
Every failure returns a clear error plus the suggestion to use Paste mode, and
never raises — the demo must keep working fully offline.
"""

import requests

from src.config import MAX_CONTENT_CHARS, REQUEST_TIMEOUT, USER_AGENT

PASTE_SUGGESTION = (
    "Could not fetch this URL. Copy the page HTML (View Source) or its text and "
    "use Paste mode instead — the audit works identically on pasted content."
)


def fetch_page(url: str) -> dict:
    """Return {ok, url, final_url, status_code, html, error, suggestion}."""
    result = {
        "ok": False,
        "url": url,
        "final_url": None,
        "status_code": None,
        "html": None,
        "error": None,
        "suggestion": None,
    }
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
        "Accept-Language": "en,th;q=0.8",
    }
    try:
        response = requests.get(
            url, headers=headers, timeout=REQUEST_TIMEOUT, allow_redirects=True
        )
        result["status_code"] = response.status_code
        result["final_url"] = str(response.url)
        if response.status_code >= 400:
            result["error"] = f"Server returned HTTP {response.status_code}."
            result["suggestion"] = PASTE_SUGGESTION
            return result

        content_type = (response.headers.get("Content-Type") or "").lower()
        if content_type and not any(
            t in content_type for t in ("text/html", "application/xhtml", "text/plain", "text/markdown")
        ):
            result["error"] = f"URL is not an HTML/text page (Content-Type: {content_type})."
            result["suggestion"] = PASTE_SUGGESTION
            return result

        if not response.encoding or response.encoding.lower() == "iso-8859-1":
            response.encoding = response.apparent_encoding or "utf-8"
        html = response.text or ""
        if len(html) > MAX_CONTENT_CHARS * 4:
            html = html[: MAX_CONTENT_CHARS * 4]
        if not html.strip():
            result["error"] = "Server returned an empty document."
            result["suggestion"] = PASTE_SUGGESTION
            return result

        result["ok"] = True
        result["html"] = html
        return result

    except requests.exceptions.Timeout:
        result["error"] = f"Request timed out after {REQUEST_TIMEOUT}s."
    except requests.exceptions.SSLError:
        result["error"] = "SSL certificate verification failed."
    except requests.exceptions.ConnectionError:
        result["error"] = "Connection failed (site unreachable or offline)."
    except requests.exceptions.RequestException as exc:
        result["error"] = f"Request failed: {exc.__class__.__name__}."
    except Exception as exc:  # absolute backstop: fetching must never crash the app
        result["error"] = f"Unexpected error while fetching: {exc.__class__.__name__}."
    result["suggestion"] = PASTE_SUGGESTION
    return result
