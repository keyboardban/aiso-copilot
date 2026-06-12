"""Sourceability / citation-readiness scoring.

Estimates whether the page contains enough explicit, quotable evidence for an
AI-assisted search system to use it as a source. A weighted evidence checklist
(weights sum to 100) — fully deterministic and explainable.
"""

import re

from src.audit.structure_audit import (
    CASE_RE,
    DEFINITION_RE,
    EXAMPLE_RE,
    METRIC_RE,
    TRUST_RE,
    _detect_process_steps,
)

METHOD_RE = re.compile(r"\bmethod(?:ology)?\b|\bapproach\b|\bframework\b|\baudit\b|\bprocess\b|กระบวนการ|ขั้นตอน", re.I)
COMPARISON_RE = re.compile(r"\bvs\b|\bversus\b|different from|difference between|compared (?:to|with)|\bunlike\b|ต่างจาก|แตกต่าง", re.I)
AUTHOR_RE = re.compile(r"written by|\bby [A-Z][a-z]+ [A-Z][a-z]+|\bauthor\b|เขียนโดย")
DATE_RE = re.compile(r"\b(?:updated|published|last modified|reviewed)\b.{0,30}\d|\b20\d\d\b|อัปเดต(?:เมื่อ)?", re.I)
PHONE_RE = re.compile(r"(?:\+|0)\d[\d\s().-]{7,}\d")

_WHY = {
    "clear_definition": "AI answers to 'what is X' questions quote pages that define X explicitly.",
    "specific_examples": "Examples make claims concrete enough to be reused in a generated answer.",
    "step_process": "Step-by-step structure is among the most quotable content shapes for 'how to' answers.",
    "methodology": "A named methodology signals first-hand expertise rather than aggregated content.",
    "comparison": "Comparison passages get retrieved for the high-volume 'X vs Y' question family.",
    "metrics_outcomes": "Concrete numbers are citation currency — vague claims cannot be quoted as facts.",
    "case_proof": "Case studies/client outcomes give systems verifiable evidence to recommend you on.",
    "author_company_trust": "Systems prefer sources with an identifiable, credible author or organization.",
    "freshness": "Visible dates let systems judge whether the information is current.",
    "support_pages": "About/contact pages let systems verify the entity behind the claims.",
    "internal_support": "Internal links to related content show topical depth beyond one page.",
    "external_refs": "Citing external sources signals researched, verifiable content.",
    "schema_support": "Structured data confirms the page's entities and purpose machine-readably.",
    "schema_consistency": "Markup that contradicts visible text erodes machine trust.",
    "naming_clarity": "Consistent topic naming across title and H1 removes entity ambiguity.",
}

_RECOMMENDATIONS = {
    "clear_definition": "Open the page with a 2–3 sentence definition of the core service/topic.",
    "specific_examples": "Add concrete examples to your main claims ('for example, a Bangkok hotel could…').",
    "step_process": "Present your methodology as numbered steps, one clear action per step.",
    "methodology": "Name and describe your methodology or framework explicitly.",
    "comparison": "Add a section comparing your topic to the nearest familiar alternative.",
    "metrics_outcomes": "Replace vague outcome language with at least two concrete numbers (ranges are fine).",
    "case_proof": "Publish at least one case study or named client outcome and link it from this page.",
    "author_company_trust": "Add an author byline or a short 'who we are' block with credentials.",
    "freshness": "Show a visible 'last updated' date and keep it honest.",
    "support_pages": "Link to your About and Contact pages from this page.",
    "internal_support": "Add internal links to 2–3 related guides or service pages.",
    "external_refs": "Reference at least one authoritative external source.",
    "schema_support": "Add JSON-LD for the types this page supports (see Schema tab).",
    "schema_consistency": "Align schema fields exactly with what the visible content says.",
    "naming_clarity": "Use one consistent name for the service in the title, H1, and body.",
}


def assess_sourceability(page: dict, entity_result: dict) -> dict:
    """Return {sourceability_score, strong_evidence, missing_evidence,
    recommendations, checks}."""
    entities = entity_result.get("entities", {})
    body = page.get("body_text", "")
    title = page.get("title", "")
    h1_list = page.get("headings", {}).get("h1", [])
    links = page.get("links", {"internal": [], "external": []})
    json_ld = page.get("json_ld", [])
    checks = []

    def check(check_id, label, weight, passed, details=""):
        checks.append({"id": check_id, "label": label, "weight": weight,
                       "passed": bool(passed), "details": details})

    check("clear_definition", "Clear definition of the core topic", 10,
          bool(DEFINITION_RE.search(body)))
    check("specific_examples", "Specific examples", 8, bool(EXAMPLE_RE.search(body)))
    check("step_process", "Step-by-step process", 10, _detect_process_steps(page.get("sections", [])))
    check("methodology", "Named methodology / framework", 6, bool(METHOD_RE.search(body)))
    check("comparison", "Comparison explanation", 6, bool(COMPARISON_RE.search(body)))

    metric_hits = len(METRIC_RE.findall(body))
    check("metrics_outcomes", "Metrics or measurable outcomes (≥2 numeric facts)", 10,
          metric_hits >= 2, f"{metric_hits} numeric fact(s) found")
    check("case_proof", "Case study or client proof point", 10,
          bool(CASE_RE.search(body)) or bool(entities.get("proof_points")))

    org_in_schema = any(t in ("Organization", "LocalBusiness") for t in page.get("json_ld_types", []))
    check("author_company_trust", "Identifiable author or organization", 8,
          org_in_schema or bool(AUTHOR_RE.search(body)) or bool(TRUST_RE.search(body)))
    check("freshness", "Visible date / freshness signal", 6,
          bool(DATE_RE.search(body)) or "dateModified" in str(json_ld) or "datePublished" in str(json_ld))

    internal = links.get("internal", [])
    support_link = any(re.search(r"about|contact|team", (l.get("href", "") + l.get("text", "")), re.I)
                       for l in internal)
    check("support_pages", "Links to about/contact supporting pages", 5, support_link)
    check("internal_support", "Internal links to supporting content (≥3)", 5,
          len(internal) >= 3, f"{len(internal)} internal link(s)")
    check("external_refs", "External references where relevant", 6,
          len(links.get("external", [])) >= 1, f"{len(links.get('external', []))} external link(s)")

    check("schema_support", "Structured data present", 5, bool(json_ld),
          ", ".join(page.get("json_ld_types", [])[:4]))
    schema_names = re.findall(r'"name"\s*:\s*"([^"]+)"', str(json_ld))
    schema_consistent = bool(json_ld) and not page.get("json_ld_errors") and (
        not schema_names or any(n.lower() in (body + title).lower() for n in schema_names)
    )
    check("schema_consistency", "Visible content supports the structured data", 3, schema_consistent)

    topic_tokens = [t for t in re.findall(r"[a-z]{3,}", title.lower()) if t not in ("services", "service")]
    h1_text = " ".join(h1_list).lower()
    naming_clear = bool(h1_list) and sum(1 for t in topic_tokens[:6] if t in h1_text) >= 2
    check("naming_clarity", "Low ambiguity: title and H1 name the same topic", 2, naming_clear)

    total = sum(c["weight"] for c in checks)
    passed = sum(c["weight"] for c in checks if c["passed"])
    score = round(100 * passed / total) if total else 0

    strong_evidence = [
        c["label"] + (f" — {c['details']}" if c["details"] else "")
        for c in sorted(checks, key=lambda c: -c["weight"]) if c["passed"]
    ][:10]
    missing_evidence = [
        f"{c['label']} — {_WHY.get(c['id'], '')}"
        for c in sorted(checks, key=lambda c: -c["weight"]) if not c["passed"]
    ]
    recommendations = [
        _RECOMMENDATIONS[c["id"]]
        for c in sorted(checks, key=lambda c: -c["weight"])
        if not c["passed"] and c["id"] in _RECOMMENDATIONS
    ]

    return {
        "sourceability_score": score,
        "strong_evidence": strong_evidence,
        "missing_evidence": missing_evidence,
        "recommendations": recommendations,
        "checks": checks,
    }
