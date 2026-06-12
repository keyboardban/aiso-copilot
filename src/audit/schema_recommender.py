"""Schema.org recommendation with a JSON-LD preview.

Recommends only schema types the visible content can support, and builds the
preview strictly from extracted page content — never invented fields. Schema
is framed as machine-readability support, not a visibility guarantee.
"""

import re
from urllib.parse import urlparse

from src.audit.structure_audit import DEFINITION_RE
from src.audit.sourceability import AUTHOR_RE, DATE_RE, PHONE_RE
from src.utils.text import split_sentences, truncate

STANDARD_WARNINGS = [
    "Only use schema fields that are supported by visible page content.",
    "Validate the JSON-LD with Google's Rich Results Test before deploying.",
    "Structured data improves machine readability; it does not guarantee AI Search visibility or citations.",
    "Keep the markup in sync whenever the visible content changes.",
]


def _site_origin(page: dict) -> str:
    url = page.get("url") or ""
    if url:
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    for obj in page.get("json_ld", []):
        if isinstance(obj, dict) and isinstance(obj.get("url"), str):
            return obj["url"]
    return ""


def _definition_sentence(page: dict, service_name: str) -> str:
    """First visible sentence that defines the service — used as description."""
    needle = service_name.split("(")[0].strip().lower()
    for sentence in split_sentences(page.get("body_text", ""))[:40]:
        if DEFINITION_RE.search(sentence) and needle and needle in sentence.lower():
            return truncate(sentence, 250)
    return ""


def recommend_schema(page: dict, entity_result: dict) -> dict:
    """Return {recommended_schema_types, json_ld_preview, warnings,
    schema_score, existing_types, missing_types, notes}."""
    entities = entity_result.get("entities", {})
    body = page.get("body_text", "")
    faq_blocks = [b for b in page.get("faq_blocks", []) if len(b.get("answer", "")) >= 15]
    existing_types = page.get("json_ld_types", [])
    notes = []

    brand = entities.get("brand", [])
    services = entities.get("services", [])
    locations = entities.get("locations", [])
    audiences = entities.get("audiences", [])
    title_h1 = (page.get("title", "") + " " + " ".join(page.get("headings", {}).get("h1", []))).lower()
    is_service_page = bool(services) and (
        "service" in title_h1 or any(s.split("(")[0].strip().lower() in title_h1 for s in services)
    )

    recommended = []
    if brand:
        recommended.append("Organization")
    if is_service_page:
        recommended.append("Service")
    if len(faq_blocks) >= 2:
        recommended.append("FAQPage")
    if not is_service_page and page.get("word_count", 0) >= 400 and (
        AUTHOR_RE.search(body) or DATE_RE.search(body)
    ):
        recommended.append("Article")
    url = page.get("url") or ""
    path_segments = [s for s in urlparse(url).path.split("/") if s] if url else []
    if len(path_segments) >= 2:
        recommended.append("BreadcrumbList")

    if PHONE_RE.search(body) and locations:
        recommended.append("LocalBusiness")
    else:
        notes.append(
            "LocalBusiness not recommended: no visible address/phone on the page. "
            "Add NAP details first if a local profile matters to you."
        )
    if "Article" not in recommended and not is_service_page:
        notes.append("Article not recommended: no visible author or publish date to mark up.")

    # --- JSON-LD preview built only from extracted visible content -----------
    graph = []
    origin = _site_origin(page)

    if "Organization" in recommended:
        org = {"@type": "Organization", "name": brand[0]}
        if origin:
            org["url"] = origin
        if page.get("meta_description"):
            org["description"] = page["meta_description"]
        graph.append(org)

    if "Service" in recommended:
        service_name = services[0]
        service = {
            "@type": "Service",
            "name": service_name,
            "serviceType": service_name.split("(")[0].strip(),
        }
        if brand:
            service["provider"] = {"@type": "Organization", "name": brand[0]}
        if locations:
            service["areaServed"] = locations[:3]
        if audiences:
            service["audience"] = {"@type": "Audience", "audienceType": audiences[0]}
        description = _definition_sentence(page, service_name) or page.get("meta_description", "")
        if description:
            service["description"] = description
        graph.append(service)

    if "FAQPage" in recommended:
        graph.append({
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": block["question"],
                    "acceptedAnswer": {"@type": "Answer", "text": block["answer"]},
                }
                for block in faq_blocks[:8]
            ],
        })

    if "BreadcrumbList" in recommended:
        items = []
        for position, segment in enumerate(path_segments, start=1):
            items.append({
                "@type": "ListItem",
                "position": position,
                "name": segment.replace("-", " ").replace("_", " ").title(),
                "item": f"{origin}/{'/'.join(path_segments[:position])}" if origin else None,
            })
        items = [{k: v for k, v in item.items() if v is not None} for item in items]
        graph.append({"@type": "BreadcrumbList", "itemListElement": items})

    preview = {"@context": "https://schema.org", "@graph": graph} if graph else {}

    # --- consistency notes on existing markup --------------------------------
    if "FAQPage" in existing_types and len(faq_blocks) < 2:
        notes.append("Existing FAQPage markup found, but little visible Q&A content backs it up — align them.")
    for error in page.get("json_ld_errors", []):
        notes.append(f"Existing structured data has a problem: {error}")

    # --- transparent schema score (see SCORING_RUBRIC.md) ---------------------
    has_json_ld = bool(page.get("json_ld"))
    base_valid = 25 if has_json_ld else 0
    error_free = 10 if has_json_ld and not page.get("json_ld_errors") else 0
    if recommended:
        covered = len(set(existing_types) & set(recommended))
        alignment = round(35 * covered / len(recommended))
    else:
        alignment = 35 if has_json_ld else 0
    feasibility_signals = [
        bool(brand),
        bool(services or entities.get("products")),
        len(faq_blocks) >= 2,
        bool(page.get("meta_description")),
    ]
    feasibility = round(30 * sum(feasibility_signals) / len(feasibility_signals))
    schema_score = min(100, base_valid + error_free + alignment + feasibility)

    missing_types = [t for t in recommended if t not in existing_types]

    return {
        "recommended_schema_types": recommended,
        "json_ld_preview": preview,
        "warnings": list(STANDARD_WARNINGS),
        "schema_score": schema_score,
        "existing_types": existing_types,
        "missing_types": missing_types,
        "notes": notes,
        "score_parts": {
            "existing_markup": base_valid,
            "error_free": error_free,
            "alignment_with_recommended": alignment,
            "content_feasibility": feasibility,
        },
    }
