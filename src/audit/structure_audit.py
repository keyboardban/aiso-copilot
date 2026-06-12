"""Rule-based structure audit for AI Search readiness.

A weighted checklist (~23 checks) over the structured page object. Every check
records pass/fail with details, so the score is fully explainable and matches
SCORING_RUBRIC.md. No LLM involvement.
"""

import re

DEFINITION_RE = re.compile(
    r"\b(?:is|are) (?:the|a|an)\b|also called|also known as|known as|refers to|"
    r"is the practice|means\b|คือ|หมายถึง", re.I)
EXAMPLE_RE = re.compile(r"for example|for instance|e\.g\.|such as|ตัวอย่างเช่น|เช่น", re.I)
METRIC_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:%|percent|x\b)|\b(?:ctr|kpi|roi|impressions?|conversion rate)\b", re.I)
CASE_RE = re.compile(r"case stud|client story|testimonial|success story|ผลงานลูกค้า|เคสตัวอย่าง", re.I)
TRUST_RE = re.compile(
    r"about us|our team|contact us|since \d{4}|certified|award|partner|trusted by|"
    r"ติดต่อเรา|เกี่ยวกับเรา|ทีมงาน", re.I)
PROCESS_HEADING_RE = re.compile(r"process|steps?|methodology|how (?:we|it) work|workflow|ขั้นตอน|วิธีการ", re.I)
STEP_HEADING_RE = re.compile(r"^(?:\d+[.)]?\s|step\b)", re.I)


def _check(checks: list, check_id: str, label: str, weight: int, passed: bool, details: str = "") -> None:
    checks.append({
        "id": check_id, "label": label, "weight": weight,
        "passed": bool(passed), "details": details,
    })


def _count_direct_answer_blocks(sections: list) -> int:
    count = 0
    for sec in sections:
        content = sec.get("content", "")
        if not content:
            continue
        first_line = content.splitlines()[0]
        is_question_heading = sec.get("heading", "").rstrip().endswith("?")
        starts_definitionally = bool(DEFINITION_RE.search(first_line[:180]))
        if (is_question_heading and len(first_line.split()) >= 8) or starts_definitionally:
            count += 1
    return count


def _detect_process_steps(sections: list) -> bool:
    # numbered / "Step" headings
    step_headings = sum(1 for s in sections if STEP_HEADING_RE.match(s.get("heading", "")))
    if step_headings >= 3:
        return True
    # a process-titled section followed by >=3 deeper subsections
    for i, sec in enumerate(sections):
        if sec.get("heading") and PROCESS_HEADING_RE.search(sec["heading"]):
            level = sec.get("level", 0)
            children = 0
            for nxt in sections[i + 1:]:
                if nxt.get("level", 0) <= level and nxt.get("heading"):
                    break
                children += 1
            if children >= 3:
                return True
    # ordered-list style lines inside one section
    for sec in sections:
        numbered_lines = sum(1 for line in sec.get("content", "").splitlines()
                             if re.match(r"^\s*\d+[.)]\s", line))
        if numbered_lines >= 3:
            return True
    return False


def audit_structure(page: dict, entity_result: dict) -> dict:
    """Return {structure_score, strengths, weaknesses, recommendations, checks}."""
    checks = []
    entities = entity_result.get("entities", {})
    title = page.get("title", "")
    meta = page.get("meta_description", "")
    headings = page.get("headings", {"h1": [], "h2": [], "h3": []})
    sections = page.get("sections", [])
    body = page.get("body_text", "")
    links = page.get("links", {"internal": [], "external": []})
    faq_blocks = page.get("faq_blocks", [])

    _check(checks, "title_present", "Clear page title exists", 8, bool(title),
           f'"{title[:80]}"' if title else "No title found")
    _check(checks, "title_length", "Title length is snippet-friendly (15–70 chars)", 2,
           15 <= len(title) <= 70, f"{len(title)} characters")
    _check(checks, "meta_present", "Meta description exists", 6, bool(meta))
    _check(checks, "meta_length", "Meta description length 70–170 chars", 2,
           70 <= len(meta) <= 170, f"{len(meta)} characters")

    h1_count = len(headings.get("h1", []))
    _check(checks, "h1_present", "H1 exists", 8, h1_count >= 1, f"{h1_count} H1 heading(s)")
    _check(checks, "h1_single", "Exactly one H1 (no duplication)", 3, h1_count == 1,
           f"{h1_count} H1 heading(s)")

    sub_headings = headings.get("h2", []) + headings.get("h3", [])
    descriptive = [h for h in sub_headings if 2 <= len(h.split()) <= 12]
    _check(checks, "headings_descriptive", "H2/H3 headings are descriptive (≥3, 2–12 words)", 6,
           len(descriptive) >= 3, f"{len(descriptive)} descriptive subheadings of {len(sub_headings)}")

    direct_answers = _count_direct_answer_blocks(sections)
    _check(checks, "direct_answers", "Direct answer-style blocks (question heading → immediate answer)", 8,
           direct_answers >= 2, f"{direct_answers} direct-answer block(s) detected")
    _check(checks, "definitions", "Explicit definitions present ('X is…', 'also called…', 'คือ')", 6,
           bool(DEFINITION_RE.search(body)))

    _check(checks, "faq_present", "FAQ / Q&A-style content exists (≥2 Q&A blocks)", 8,
           len(faq_blocks) >= 2, f"{len(faq_blocks)} Q&A block(s) detected")
    substantial = [b for b in faq_blocks if len(b.get("answer", "").split()) >= 25]
    _check(checks, "faq_depth", "FAQ depth (≥4 blocks with substantial answers)", 3,
           len(faq_blocks) >= 4 and len(substantial) >= 3,
           f"{len(faq_blocks)} blocks, {len(substantial)} with substantial answers")

    _check(checks, "internal_links", "Internal links to supporting pages (≥2)", 5,
           len(links.get("internal", [])) >= 2, f"{len(links.get('internal', []))} internal link(s)")
    _check(checks, "external_links", "External reference links (≥1)", 4,
           len(links.get("external", [])) >= 1, f"{len(links.get('external', []))} external link(s)")

    _check(checks, "service_clarity", "Service/product offering is identifiable", 6,
           bool(entities.get("services") or entities.get("products")),
           ", ".join(entities.get("services", [])[:3]))
    brand = entities.get("brand", [])
    brand_visible = bool(brand) and (
        (brand[0].lower() in title.lower()) or (brand[0].lower() in body.lower())
    )
    _check(checks, "brand_clarity", "Brand/entity is named and visible in content", 6,
           brand_visible, brand[0] if brand else "No brand detected")
    _check(checks, "audience_clarity", "Target audience is named", 5,
           bool(entities.get("audiences")), ", ".join(entities.get("audiences", [])[:3]))
    _check(checks, "location_clarity", "Location/market is named (if relevant)", 3,
           bool(entities.get("locations")), ", ".join(entities.get("locations", [])[:3]))

    _check(checks, "examples", "Concrete examples present", 5, bool(EXAMPLE_RE.search(body)))
    _check(checks, "process_steps", "Process / steps / methodology section", 6,
           _detect_process_steps(sections))
    metric_hits = len(METRIC_RE.findall(body))
    _check(checks, "metrics_present", "Metrics or measurable outcomes (≥2 numeric facts)", 5,
           metric_hits >= 2, f"{metric_hits} numeric/measurement mention(s)")
    _check(checks, "case_studies", "Case studies or client proof", 4, bool(CASE_RE.search(body)))

    link_text = " ".join(
        (l.get("href", "") + " " + l.get("text", "")) for l in links.get("internal", [])
    )
    trust = bool(TRUST_RE.search(body)) or bool(re.search(r"about|contact|team", link_text, re.I))
    _check(checks, "trust_signals", "Trust signals (about/contact/team, credentials)", 4, trust)

    has_schema = bool(page.get("json_ld"))
    _check(checks, "schema_present", "Structured data (JSON-LD) present", 4, has_schema,
           ", ".join(page.get("json_ld_types", [])[:4]) or "None found")
    schema_matches = False
    if has_schema:
        names = re.findall(r'"name"\s*:\s*"([^"]+)"', str(page.get("json_ld")))
        schema_matches = (not names) or any(n.lower() in body.lower() or n.lower() in title.lower()
                                            for n in map(str, names))
        schema_matches = schema_matches and not page.get("json_ld_errors")
    _check(checks, "schema_matches", "Schema content matches visible text", 3, schema_matches,
           "No JSON-LD to compare" if not has_schema else "")

    total_weight = sum(c["weight"] for c in checks)
    passed_weight = sum(c["weight"] for c in checks if c["passed"])
    score = round(100 * passed_weight / total_weight) if total_weight else 0

    strengths = [
        c["label"] + (f" — {c['details']}" if c["details"] else "")
        for c in sorted(checks, key=lambda c: -c["weight"]) if c["passed"] and c["weight"] >= 5
    ][:8]
    weaknesses = [
        c["label"] + (f" — {c['details']}" if c["details"] else "")
        for c in sorted(checks, key=lambda c: -c["weight"]) if not c["passed"]
    ]

    recommendations_map = {
        "title_present": "Add a descriptive <title> that names the service, market, and brand.",
        "title_length": "Adjust the title to ~15–70 characters so it survives snippeting intact.",
        "meta_present": "Add a meta description that summarizes the page's answer in plain language.",
        "meta_length": "Rewrite the meta description to ~70–170 characters.",
        "h1_present": "Add a single, descriptive H1 naming the topic and audience.",
        "h1_single": "Keep exactly one H1; demote the others to H2.",
        "headings_descriptive": "Rewrite H2/H3 headings as descriptive statements or questions (2–12 words).",
        "direct_answers": "Open key sections with a direct 2–3 sentence answer before elaborating.",
        "definitions": "Add explicit definitions ('X is …', 'also called …') for your core terms.",
        "faq_present": "Add an FAQ section answering your customers' most common questions.",
        "faq_depth": "Expand the FAQ to 4+ questions with substantial 40+ word answers.",
        "internal_links": "Link to supporting pages (related services, guides, about/contact).",
        "external_links": "Reference at least one authoritative external source where relevant.",
        "service_clarity": "Name the service/product explicitly and repeat it consistently.",
        "brand_clarity": "Name the brand in the title, H1, and body — consistently spelled.",
        "audience_clarity": "State who the page is for ('for Thai SMEs', 'for marketing teams').",
        "location_clarity": "Name your market (country/city) if you serve a specific one.",
        "examples": "Add concrete examples ('for example…') to abstract claims.",
        "process_steps": "Describe your process as numbered steps with one action each.",
        "metrics_present": "Add at least two concrete numbers (results, benchmarks, timelines).",
        "case_studies": "Add a case study or named client outcome.",
        "trust_signals": "Add trust signals: about/contact links, team, credentials, or history.",
        "schema_present": "Add JSON-LD structured data matching the visible content (see Schema tab).",
        "schema_matches": "Keep every schema field backed by visible page text and free of parse errors.",
    }
    recommendations = [
        recommendations_map[c["id"]] for c in sorted(checks, key=lambda c: -c["weight"])
        if not c["passed"] and c["id"] in recommendations_map
    ]

    return {
        "structure_score": score,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "recommendations": recommendations,
        "checks": checks,
    }
