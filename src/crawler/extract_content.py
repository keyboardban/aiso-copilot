"""Turn raw HTML / Markdown / plain text into one structured page object.

This is the contract every downstream module depends on:

    {
      "source_type", "url", "title", "meta_description",
      "headings": {"h1": [], "h2": [], "h3": []},
      "body_text": str,
      "sections": [{"heading", "level", "content", "word_count"}],
      "links": {"internal": [{"text", "href"}], "external": [...]},
      "faq_blocks": [{"question", "answer"}],
      "json_ld": [], "json_ld_types": [], "json_ld_errors": [],
      "microdata_types": [],
      "word_count": int,
      "technical_extractability": {"status", "score", "issues"},
      "extractor": str,
    }

HTML parsing uses BeautifulSoup (lxml when available); trafilatura, when
installed, supplies cleaner main-body text for real-world pages. Markdown is
parsed directly (headings, links, frontmatter) so even a bare Python install
can run the demo.
"""

import re
from urllib.parse import urlparse

from src.config import MAX_CONTENT_CHARS
from src.crawler.parse_schema import parse_json_ld_from_soup, parse_microdata_types
from src.input.validators import looks_like_html
from src.utils.text import normalize_ws, truncate, word_count

try:
    from bs4 import BeautifulSoup

    _HAS_BS4 = True
except ImportError:  # pragma: no cover - bs4 is in requirements.txt
    _HAS_BS4 = False

try:
    import trafilatura

    _HAS_TRAFILATURA = True
except ImportError:
    _HAS_TRAFILATURA = False

_FAQ_HEADING_RE = re.compile(
    r"\bfaq\b|frequently asked|q\s*&\s*a|common questions|คำถามที่พบบ่อย|คำถาม", re.I
)
_QA_INLINE_RE = re.compile(r"^\s*(?:Q|Question)\s*[:.]\s*(.+)$", re.I)
_QA_ANSWER_RE = re.compile(r"^\s*(?:A|Answer)\s*[:.]\s*(.+)$", re.I)


# --------------------------------------------------------------------------- #
# Markdown parsing
# --------------------------------------------------------------------------- #

def _parse_frontmatter(text: str) -> tuple:
    """Parse a simple `--- key: value ---` frontmatter block. Returns (meta, rest)."""
    meta = {}
    if not text.startswith("---"):
        return meta, text
    end = text.find("\n---", 3)
    if end == -1 or end > 2000:
        return meta, text
    block = text[3:end]
    for line in block.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip().lower()
            if key in ("title", "description", "meta_description"):
                meta["description" if key == "meta_description" else key] = value.strip().strip("\"'")
    rest = text[end + 4 :].lstrip("-").lstrip("\n")
    return meta, rest


_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_MD_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def _clean_md_inline(line: str) -> str:
    """Strip inline markdown syntax but keep the text (used for headings too,
    so numbering like '1. Audit' survives for process-step detection)."""
    line = _MD_IMAGE_RE.sub(r"\1", line)
    line = _MD_LINK_RE.sub(r"\1", line)
    line = re.sub(r"[*_`]{1,3}", "", line)  # emphasis / inline code markers
    line = line.replace("|", " ")  # table pipes
    return line.strip()


def _clean_md_line(line: str) -> str:
    line = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", line)  # bullets / numbering
    line = re.sub(r"^\s*>\s?", "", line)  # blockquotes
    return _clean_md_inline(line)


def _markdown_to_structure(text: str) -> dict:
    meta, body = _parse_frontmatter(text)

    # collect links before stripping markdown syntax
    raw_links = [
        {"text": m.group(1).strip(), "href": m.group(2).strip()}
        for m in _MD_LINK_RE.finditer(body)
    ]

    # drop fenced code blocks (rarely quotable evidence, often noise)
    body = re.sub(r"```.*?```", "", body, flags=re.S)

    headings = {"h1": [], "h2": [], "h3": []}
    sections = []
    current = {"heading": "", "level": 0, "lines": []}

    for line in body.splitlines():
        heading_match = _MD_HEADING_RE.match(line)
        if heading_match:
            sections.append(current)
            level = len(heading_match.group(1))
            heading_text = _clean_md_inline(heading_match.group(2))
            if 1 <= level <= 3:
                headings[f"h{level}"].append(heading_text)
            current = {"heading": heading_text, "level": level, "lines": []}
        else:
            cleaned = _clean_md_line(line)
            current["lines"].append(cleaned)
    sections.append(current)

    built = _build_sections(sections)
    body_text = "\n".join(
        part for sec in built for part in (sec["heading"], sec["content"]) if part
    )
    title = meta.get("title") or (headings["h1"][0] if headings["h1"] else "")

    return {
        "title": title,
        "meta_description": meta.get("description", ""),
        "headings": headings,
        "sections": built,
        "raw_links": raw_links,
        "body_text": body_text,
        "json_ld": [],
        "json_ld_types": [],
        "json_ld_errors": [],
        "microdata_types": [],
        "noindex": False,
        "extractor": "markdown",
    }


def _build_sections(raw_sections: list) -> list:
    sections = []
    for sec in raw_sections:
        content_lines = [l for l in sec.get("lines", []) if l]
        content = "\n".join(content_lines).strip()
        if not content and not sec.get("heading"):
            continue
        sections.append(
            {
                "heading": sec.get("heading", ""),
                "level": sec.get("level", 0),
                "content": content,
                "word_count": word_count(content),
            }
        )
    return sections


# --------------------------------------------------------------------------- #
# HTML parsing
# --------------------------------------------------------------------------- #

def _make_soup(html: str):
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


def _html_to_structure(html: str, url: str = None) -> dict:
    soup = _make_soup(html)

    schema = parse_json_ld_from_soup(soup)
    microdata_types = parse_microdata_types(soup)

    title = ""
    if soup.title and soup.title.string:
        title = normalize_ws(soup.title.string)
    meta_description = ""
    meta_tag = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    if meta_tag and meta_tag.get("content"):
        meta_description = normalize_ws(meta_tag["content"])
    noindex = False
    robots_tag = soup.find("meta", attrs={"name": re.compile(r"^robots$", re.I)})
    if robots_tag and "noindex" in (robots_tag.get("content") or "").lower():
        noindex = True

    # links from the whole document (footer/nav links are useful trust signals)
    raw_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:")):
            continue
        raw_links.append({"text": normalize_ws(a.get_text(" "))[:120], "href": href})

    # strip non-content elements, then pick the densest content root
    for tag in soup.find_all(["script", "style", "noscript", "template", "svg", "iframe", "form", "button"]):
        tag.decompose()
    root = soup.body or soup
    for candidate_name in ("main", "article"):
        candidate = soup.find(candidate_name)
        if candidate and len(candidate.get_text(strip=True)) > 200:
            root = candidate
            break
    if root is soup.body or root is soup:
        for tag in soup.find_all(["nav", "header", "footer", "aside"]):
            tag.decompose()

    headings = {"h1": [], "h2": [], "h3": []}
    raw_sections = []
    current = {"heading": "", "level": 0, "lines": []}
    for el in root.find_all(["h1", "h2", "h3", "h4", "p", "ul", "ol", "table", "blockquote", "pre"]):
        name = el.name
        if name in ("h1", "h2", "h3", "h4"):
            raw_sections.append(current)
            # separator=" " prevents inline children from mashing together
            # (e.g. <h2><span>DATA-LED</span><span>CREATIVE-POWERED</span></h2>)
            heading_text = normalize_ws(el.get_text(" "))
            level = int(name[1])
            if level <= 3 and heading_text:
                headings[f"h{level}"].append(heading_text)
            current = {"heading": heading_text, "level": level, "lines": []}
            continue
        if name in ("p", "blockquote") and el.find_parent(["ul", "ol", "table", "blockquote"]):
            continue  # already captured by the ancestor element
        if name in ("ul", "ol") and el.find_parent(["ul", "ol", "table"]):
            continue
        if name in ("ul", "ol"):
            items = [normalize_ws(li.get_text(" ")) for li in el.find_all("li", recursive=False)]
            text = "\n".join(i for i in items if i)
        else:
            text = normalize_ws(el.get_text(" "))
        if text:
            current["lines"].append(text)
    raw_sections.append(current)

    built = _build_sections(raw_sections)
    body_text = "\n".join(
        part for sec in built for part in (sec["heading"], sec["content"]) if part
    )

    # trafilatura (optional) often extracts cleaner body text on real pages
    extractor = "beautifulsoup"
    if _HAS_TRAFILATURA:
        try:
            extracted = trafilatura.extract(html, include_comments=False, include_tables=True)
        except Exception:
            extracted = None
        if extracted and len(extracted) > len(body_text) * 0.6:
            body_text = extracted
            extractor = "trafilatura+beautifulsoup"

    return {
        "title": title,
        "meta_description": meta_description,
        "headings": headings,
        "sections": built,
        "raw_links": raw_links,
        "body_text": body_text,
        "json_ld": schema["json_ld"],
        "json_ld_types": schema["types"],
        "json_ld_errors": schema["parse_errors"],
        "microdata_types": microdata_types,
        "noindex": noindex,
        "extractor": extractor,
    }


# --------------------------------------------------------------------------- #
# Shared post-processing
# --------------------------------------------------------------------------- #

def _classify_links(raw_links: list, url: str = None) -> dict:
    base_host = urlparse(url).netloc.lower() if url else ""
    internal, external = [], []
    seen = set()
    for link in raw_links:
        href = link.get("href", "")
        if not href or href in seen:
            continue
        seen.add(href)
        parsed = urlparse(href)
        if parsed.scheme in ("http", "https"):
            if base_host and parsed.netloc.lower() == base_host:
                internal.append(link)
            else:
                external.append(link)
        else:
            internal.append(link)  # relative / fragment links
    return {"internal": internal, "external": external}


def _detect_faq_blocks(sections: list) -> list:
    blocks = []
    seen = set()
    faq_zone_level = None

    def add(question: str, answer: str) -> None:
        question = normalize_ws(question)
        if not question or question.lower() in seen:
            return
        seen.add(question.lower())
        blocks.append({"question": question, "answer": truncate(answer, 400)})

    for sec in sections:
        heading = sec.get("heading", "")
        level = sec.get("level", 0)
        content = sec.get("content", "")

        if faq_zone_level is not None and heading and level <= faq_zone_level:
            faq_zone_level = None  # left the FAQ container

        if heading and _FAQ_HEADING_RE.search(heading) and not heading.rstrip().endswith("?"):
            faq_zone_level = level
            # also scan container content for inline Q:/A: pairs
            pending_q = None
            for line in content.splitlines():
                q_match = _QA_INLINE_RE.match(line)
                a_match = _QA_ANSWER_RE.match(line)
                if q_match:
                    pending_q = q_match.group(1)
                elif a_match and pending_q:
                    add(pending_q, a_match.group(1))
                    pending_q = None
            continue

        if heading.rstrip().endswith("?"):
            add(heading, content)
        elif faq_zone_level is not None and heading and level > faq_zone_level and content:
            add(heading, content)

    return blocks


def _assess_extractability(page: dict, raw_len: int, source_type: str, truncated: bool) -> dict:
    issues = []
    score = 100

    if not page["title"]:
        issues.append("No page title found.")
        score -= 10
    if not page["meta_description"]:
        issues.append("No meta description found.")
        score -= 8
    if not page["headings"]["h1"]:
        issues.append("No H1 heading found.")
        score -= 10
    if not any(page["headings"].values()):
        issues.append("No heading structure at all (H1–H3 missing).")
        score -= 10

    wc = page["word_count"]
    if wc < 120:
        issues.append(f"Very little extractable text ({wc} words) — AI systems have almost nothing to retrieve.")
        score -= 30
    elif wc < 300:
        issues.append(f"Thin extractable text ({wc} words).")
        score -= 15

    if source_type == "html" and raw_len > 20_000:
        ratio = len(page["body_text"]) / raw_len
        if ratio < 0.05:
            issues.append(
                "Very low text-to-HTML ratio — main content may be rendered by JavaScript "
                "and invisible to simple crawlers."
            )
            score -= 15

    for error in page["json_ld_errors"][:2]:
        issues.append(f"Structured data problem: {error}")
        score -= 8

    if page.get("noindex"):
        issues.append("Page is set to noindex — most crawlers and AI systems will skip it.")
        score -= 20
    if truncated:
        issues.append("Input was truncated to the analysis size limit.")
        score -= 5

    score = max(0, min(100, score))
    status = "ok" if score >= 80 else ("warning" if score >= 55 else "poor")
    return {"status": status, "score": score, "issues": issues}


def extract_content(raw: str, source_type: str = "auto", url: str = None) -> dict:
    """Main entry point. ``source_type``: html | markdown | text | auto."""
    raw = raw or ""
    truncated = len(raw) > MAX_CONTENT_CHARS
    if truncated:
        raw = raw[:MAX_CONTENT_CHARS]

    if source_type == "auto":
        source_type = "html" if looks_like_html(raw) else "markdown"

    if source_type == "html" and _HAS_BS4:
        data = _html_to_structure(raw, url=url)
    elif source_type == "html":  # pragma: no cover - bs4 missing entirely
        text = re.sub(r"<[^>]+>", " ", raw)
        data = _markdown_to_structure(text)
        data["extractor"] = "regex-fallback"
    else:  # markdown and plain text share the same parser
        data = _markdown_to_structure(raw)
        if source_type == "text":
            data["extractor"] = "plaintext"

    page = {
        "source_type": source_type,
        "url": url,
        "title": data["title"],
        "meta_description": data["meta_description"],
        "headings": data["headings"],
        "body_text": data["body_text"],
        "sections": data["sections"],
        "links": _classify_links(data["raw_links"], url=url),
        "faq_blocks": _detect_faq_blocks(data["sections"]),
        "json_ld": data["json_ld"],
        "json_ld_types": data["json_ld_types"],
        "json_ld_errors": data["json_ld_errors"],
        "microdata_types": data["microdata_types"],
        "noindex": data.get("noindex", False),
        "extractor": data["extractor"],
    }
    page["word_count"] = word_count(page["body_text"])
    page["technical_extractability"] = _assess_extractability(
        page, raw_len=len(raw), source_type=source_type, truncated=truncated
    )
    return page
