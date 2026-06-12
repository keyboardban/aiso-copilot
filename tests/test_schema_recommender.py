"""Schema recommendations must be content-backed and JSON-serializable."""

import json

from src.audit.entity_extractor import extract_entities
from src.audit.schema_recommender import recommend_schema
from src.crawler.extract_content import extract_content

SERVICE_PAGE = """---
title: AI Search Optimization Services | Acme Agency
description: Acme Agency helps businesses get cited by AI search systems.
---

# AI Search Optimization Services by Acme Agency

AI Search Optimization is the practice of structuring content so AI systems can cite it.
We serve businesses across Thailand with audits and content strategy.

## What does the service include?

A full readiness audit, query fan-out mapping, and structured data implementation.

## How long does it take?

Most engagements run for three months, for example a typical SME project.
"""


def _recommend(markdown, url=None):
    page = extract_content(markdown, "markdown", url=url)
    if url:
        page["url"] = url
    entities = extract_entities(page)
    return page, recommend_schema(page, entities)


def test_recommends_content_backed_types():
    page, result = _recommend(SERVICE_PAGE)
    assert "Organization" in result["recommended_schema_types"]
    assert "Service" in result["recommended_schema_types"]
    assert "FAQPage" in result["recommended_schema_types"]
    # no address/phone on the page → LocalBusiness must NOT be recommended
    assert "LocalBusiness" not in result["recommended_schema_types"]


def test_preview_is_valid_json_and_visible_content_only():
    page, result = _recommend(SERVICE_PAGE)
    preview = result["json_ld_preview"]
    serialized = json.dumps(preview, ensure_ascii=False)  # must not raise
    assert preview["@context"] == "https://schema.org"
    faq_nodes = [n for n in preview["@graph"] if n["@type"] == "FAQPage"]
    assert faq_nodes, "FAQPage node expected"
    questions = faq_nodes[0]["mainEntity"]
    page_questions = {b["question"] for b in page["faq_blocks"]}
    assert {q["name"] for q in questions} <= page_questions, "no invented FAQ entries"
    assert "aggregateRating" not in serialized, "never fabricate ratings"


def test_required_warning_present():
    _, result = _recommend(SERVICE_PAGE)
    assert "Only use schema fields that are supported by visible page content." in result["warnings"]


def test_schema_score_bounded_and_rewards_existing_markup():
    _, bare = _recommend(SERVICE_PAGE)
    html = (
        "<html><head><title>Acme Agency Services</title>"
        '<meta name="description" content="Acme helps businesses with AI search.">'
        '<script type="application/ld+json">{"@context":"https://schema.org",'
        '"@type":"Organization","name":"Acme Agency"}</script></head>'
        "<body><h1>AI Search Optimization Services by Acme Agency</h1>"
        "<p>AI Search Optimization is the practice of structuring content. "
        "We serve businesses in Thailand.</p>"
        "<h2>Is it worth it?</h2><p>Yes, for most content-driven businesses it is.</p>"
        "<h2>How long does it take?</h2><p>Around three months for most projects.</p>"
        "</body></html>"
    )
    page = extract_content(html, "html")
    entities = extract_entities(page)
    with_markup = recommend_schema(page, entities)
    assert 0 <= bare["schema_score"] <= 100
    assert 0 <= with_markup["schema_score"] <= 100
    assert with_markup["schema_score"] > bare["schema_score"]


def test_breadcrumbs_only_with_deep_urls():
    _, result = _recommend(SERVICE_PAGE, url="https://acme.example/services/ai-search-optimization")
    assert "BreadcrumbList" in result["recommended_schema_types"]
    _, shallow = _recommend(SERVICE_PAGE, url="https://acme.example/")
    assert "BreadcrumbList" not in shallow["recommended_schema_types"]
