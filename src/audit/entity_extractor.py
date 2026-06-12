"""Deterministic entity and topic extraction.

Pulls the entities AI systems need to disambiguate a page — brand, services,
audiences, locations, problems/solutions, proof — using JSON-LD, lexicons, and
sentence patterns. Fully rule-based by design: entity extraction feeds core
scoring, so it must work identically with no LLM available.
"""

import re
from urllib.parse import urlparse

from src.utils.text import split_sentences, truncate

# (canonical display name, compiled pattern) lexicons. Thai patterns are plain
# substrings (no \b — Thai has no word boundaries).
def _lex(pairs):
    return [(name, re.compile(pattern, re.I)) for name, pattern in pairs]


SERVICE_LEXICON = _lex([
    ("AI Search Optimization", r"\bai[ -]search optimi[sz]ation\b|\baiso\b"),
    ("Generative Engine Optimization (GEO)", r"generative engine optimi[sz]ation|\bgeo\b"),
    ("Answer Engine Optimization (AEO)", r"answer engine optimi[sz]ation|\baeo\b"),
    ("SEO", r"\bseo\b|search engine optimi[sz]ation"),
    ("Content Strategy", r"content strateg"),
    ("Content Marketing", r"content marketing"),
    ("Digital Marketing", r"digital marketing"),
    ("Structured Data / Schema Implementation", r"structured data|schema\.org|schema markup|json-?ld"),
    ("AI Search Readiness Audit", r"readiness audit|ai search audit|visibility audit"),
    ("Web Analytics", r"\banalytics\b"),
    ("PPC / Paid Media", r"\bppc\b|paid media|paid search"),
    ("Web Design", r"web design|website design"),
])

INDUSTRY_LEXICON = _lex([
    ("B2B services", r"\bb2b\b"),
    ("SaaS", r"\bsaas\b"),
    ("Healthcare", r"healthcare|clinics?|hospitals?"),
    ("Hospitality & travel", r"\bhotels?\b|hospitality|travel|resorts?"),
    ("E-commerce", r"e-?commerce|online store"),
    ("Finance", r"\bfintech\b|financial services|banking"),
    ("Real estate", r"real estate|property"),
    ("Education", r"education|schools?|universit"),
    ("Retail", r"\bretail\b"),
])

LOCATION_LEXICON = _lex([
    ("Thailand", r"\bthailand\b|ประเทศไทย|เมืองไทย|ธุรกิจไทย|คนไทย|ภาษาไทย|ไทย"),
    ("Bangkok", r"\bbangkok\b|กรุงเทพ"),
    ("Chiang Mai", r"chiang ?mai|เชียงใหม่"),
    ("Phuket", r"\bphuket\b|ภูเก็ต"),
    ("Singapore", r"\bsingapore\b"),
    ("Southeast Asia", r"southeast asia"),
    ("Asia-Pacific", r"\bapac\b|asia[- ]pacific"),
])

AUDIENCE_LEXICON = _lex([
    ("Thai businesses", r"thai business|ธุรกิจไทย"),
    ("SMEs", r"\bsmes?\b|small (and|&) medium"),
    ("Marketing managers", r"marketing manager"),
    ("Founders", r"\bfounders?\b"),
    ("B2B service firms", r"b2b service"),
    ("SaaS companies", r"\bsaas\b"),
    ("E-commerce brands", r"e-?commerce"),
    ("Clinics & hospitals", r"clinics?|hospitals?"),
    ("Hotels", r"\bhotels?\b"),
    ("Enterprises", r"\benterprises?\b"),
    ("Startups", r"\bstartups?\b"),
])

TOOL_LEXICON = _lex([
    ("Google Search Console", r"search console"),
    ("Google Analytics / GA4", r"google analytics|\bga4\b"),
    ("schema.org", r"schema\.org"),
    ("ChatGPT", r"chatgpt"),
    ("Perplexity", r"perplexity"),
    ("Google Gemini", r"\bgemini\b"),
    ("Claude", r"\bclaude\b"),
    ("Microsoft Copilot / Bing", r"\bcopilot\b|\bbing\b"),
    ("n8n", r"\bn8n\b"),
    ("Ahrefs", r"\bahrefs\b"),
    ("Semrush", r"\bsemrush\b"),
    ("Screaming Frog", r"screaming frog"),
    ("WordPress", r"wordpress"),
    ("Looker Studio", r"looker studio|data studio"),
])

PROBLEM_RE = re.compile(
    r"struggle|challenge|hard to|difficult|problem|pain point|invisible|absent from|"
    r"miss(?:ing|es) out|risk of|losing|ไม่ถูก|ปัญหา|มองไม่เห็น", re.I)
SOLUTION_RE = re.compile(
    r"we help|we audit|we restructure|we assess|we expand|we add|we repair|we re-audit|"
    r"our (?:service|process|approach|team)|solution|เราช่วย|บริการของเรา", re.I)
BENEFIT_RE = re.compile(
    r"improve|increase|boost|advantage|stay visible|grow|win|benefit|easier to|"
    r"early[- ]mover|more likely|ได้เปรียบ|เพิ่ม|มองเห็นได้", re.I)
PROOF_RE = re.compile(
    r"case stud|testimonial|client (?:story|results?)|award|certified|trusted by|"
    r"\d+\+? (?:clients?|projects?|years)|portfolio|track record|ผลงาน|ลูกค้าของเรา", re.I)
METRIC_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:%|percent|x\b)|\b(?:ctr|kpi|roi|impressions?|click-?through|"
    r"conversion rate|traffic)\b|เปอร์เซ็นต์", re.I)

# Categories and weights for the clarity score (sum = 100); products are
# deliberately unweighted so service pages aren't penalized for having none.
CLARITY_WEIGHTS = {
    "brand": 15, "services": 15, "audiences": 12, "problems": 10, "solutions": 10,
    "benefits": 8, "proof_points": 8, "locations": 6, "industries": 6,
    "metrics": 6, "tools": 4,
}

_GAP_MESSAGES = {
    "brand": "No clear brand/organization name detected — AI systems may not know who this page belongs to.",
    "services": "No recognizable service offering detected in the text.",
    "audiences": "Target audience is not named explicitly.",
    "problems": "The customer problem this page addresses is never stated.",
    "solutions": "No explicit 'what we do about it' statements found.",
    "benefits": "Benefits/outcomes are not stated explicitly.",
    "proof_points": "No proof points (case studies, named results, client counts) found.",
    "locations": "No market/location signal found (add one if you serve a specific market).",
    "industries": "No industry context found (name the industries you serve if relevant).",
    "metrics": "No concrete numbers or measurable outcomes found.",
    "tools": "No tools/platforms are named (naming them adds technical credibility).",
}


def _match_lexicon(lexicon, *texts) -> list:
    combined = "\n".join(t for t in texts if t)
    return [name for name, pattern in lexicon if pattern.search(combined)]


def _matching_sentences(sentences, pattern, cap=3, max_len=170) -> list:
    found = []
    for sentence in sentences:
        if pattern.search(sentence):
            found.append(truncate(sentence, max_len))
            if len(found) >= cap:
                break
    return found


def _names_from_json_ld(json_ld: list, wanted_types: set) -> list:
    names = []

    def walk(node):
        if isinstance(node, dict):
            node_type = node.get("@type")
            types = node_type if isinstance(node_type, list) else [node_type]
            if any(t in wanted_types for t in types if t):
                name = node.get("name")
                if isinstance(name, str) and name.strip():
                    names.append(name.strip())
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(json_ld)
    return names


def _brand_candidates(page: dict) -> list:
    candidates = []
    candidates += _names_from_json_ld(
        page.get("json_ld", []), {"Organization", "LocalBusiness", "Brand", "WebSite"}
    )
    title = page.get("title", "")
    for separator in ("|", "—", "–", " - "):
        if separator in title:
            tail = title.rsplit(separator, 1)[-1].strip()
            if 2 <= len(tail) <= 60 and len(tail.split()) <= 6:
                candidates.append(tail)
            break
    if page.get("url"):
        host = urlparse(page["url"]).netloc
        core = host.split(":")[0].removeprefix("www.").split(".")[0]
        if core:
            candidates.append(core.replace("-", " ").title())
    seen, unique = set(), []
    for candidate in candidates:
        key = candidate.lower()
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def extract_entities(page: dict, target_topic: str = "", target_audience: str = "") -> dict:
    """Return the Feature-4 entity object with clarity score and gaps."""
    body = page.get("body_text", "")
    title = page.get("title", "")
    headings_text = " ".join(
        h for hs in page.get("headings", {}).values() for h in hs
    )
    sentences = split_sentences(body)

    brand = _brand_candidates(page)
    organization = _names_from_json_ld(page.get("json_ld", []), {"Organization", "LocalBusiness"}) or brand[:1]

    audiences = []
    if target_audience:
        audiences.append(target_audience)
    audiences += [a for a in _match_lexicon(AUDIENCE_LEXICON, body, title) if a not in audiences]

    entities = {
        "brand": brand,
        "organization": organization,
        "services": _match_lexicon(SERVICE_LEXICON, body, title, headings_text),
        "products": _names_from_json_ld(page.get("json_ld", []), {"Product", "SoftwareApplication"}),
        "industries": _match_lexicon(INDUSTRY_LEXICON, body),
        "locations": _match_lexicon(LOCATION_LEXICON, body, title),
        "audiences": audiences,
        "problems": _matching_sentences(sentences, PROBLEM_RE),
        "solutions": _matching_sentences(sentences, SOLUTION_RE),
        "benefits": _matching_sentences(sentences, BENEFIT_RE),
        "proof_points": _matching_sentences(sentences, PROOF_RE),
        "metrics": _matching_sentences(sentences, METRIC_RE, cap=4, max_len=140),
        "tools": _match_lexicon(TOOL_LEXICON, body),
    }

    score_breakdown = {
        category: (weight if entities.get(category) else 0)
        for category, weight in CLARITY_WEIGHTS.items()
    }
    clarity_score = sum(score_breakdown.values())

    gaps = [
        _GAP_MESSAGES[category]
        for category, weight in sorted(CLARITY_WEIGHTS.items(), key=lambda kv: -kv[1])
        if not entities.get(category)
    ]

    recommendations = []
    if not entities["brand"]:
        recommendations.append("State the brand/organization name in the title, H1, and body — and mirror it in Organization JSON-LD.")
    if not entities["audiences"]:
        recommendations.append("Name the target audience explicitly ('for Thai SMEs', 'for marketing managers').")
    if not entities["problems"] or not entities["solutions"]:
        recommendations.append("Add an explicit problem → solution passage so systems can match the page to user pain points.")
    if not entities["proof_points"]:
        recommendations.append("Add at least one verifiable proof point (case study, named client outcome, or count of projects/years).")
    if not entities["metrics"]:
        recommendations.append("Add concrete numbers (results, benchmarks, timelines) — quotable facts are citation currency.")
    if not entities["locations"]:
        recommendations.append("If you serve a specific market, name it (country/city) in the visible text.")

    return {
        "entities": entities,
        "entity_clarity_score": clarity_score,
        "score_breakdown": score_breakdown,
        "entity_gaps": gaps,
        "recommendations": recommendations[:5],
    }
