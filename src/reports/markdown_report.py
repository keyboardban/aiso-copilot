"""Client-style markdown audit report.

Fully template-based so it renders identically in no-LLM mode; the executive
summary may optionally be LLM-polished upstream (analyzer), but every section
here works from the deterministic result object alone.
"""

from datetime import datetime


def _esc(cell) -> str:
    return str(cell).replace("|", "\\|").replace("\n", " ").strip()


def _band(score: int) -> str:
    if score >= 80:
        return "Strong"
    if score >= 60:
        return "Moderate"
    if score >= 40:
        return "Developing"
    return "Needs significant work"


_SUBSCORE_MEANING = {
    "structure": "Titles, headings, direct answers, FAQ, linking",
    "entity_clarity": "Brand, services, audience, problems named explicitly",
    "query_coverage": "Fan-out questions the content can answer",
    "sourceability": "Quotable evidence: definitions, steps, numbers, proof",
    "schema": "Structured data present, valid, and content-backed",
    "technical_extractability": "How cleanly machines can extract the content",
}


def build_executive_summary(result: dict) -> str:
    """Deterministic executive summary template (LLM may polish it later)."""
    scores = result["scores"]
    subscores = scores["subscores"]
    matrix = result.get("coverage_matrix", [])
    covered = sum(1 for r in matrix if r["coverage"] == "Covered")
    partial = sum(1 for r in matrix if r["coverage"] == "Partial")
    missing = sum(1 for r in matrix if r["coverage"] == "Missing")
    title = result.get("page", {}).get("title") or "The analyzed page"
    weakest = sorted(subscores, key=subscores.get)[:2]
    weakest_text = " and ".join(
        f"{key.replace('_', ' ')} ({subscores[key]}/100)" for key in weakest
    )
    overall = scores["overall_ai_search_readiness"]

    summary = (
        f"**{title}** scores **{overall}/100 ({_band(overall)})** for estimated AI Search "
        f"readiness. Of the {len(matrix)} fan-out questions an AI assistant would likely "
        f"explore around this topic, the page currently covers {covered} fully and "
        f"{partial} partially, leaving {missing} unanswered. "
    )
    summary += (
        f"The biggest improvement levers are {weakest_text}. "
        "Addressing the priority actions below would materially improve how reliably "
        "AI-assisted search systems can understand, retrieve, and cite this page. "
        "All findings are heuristic estimates intended for human review — not "
        "guarantees of ranking or citation."
    )
    return summary


def build_markdown_report(result: dict) -> str:
    scores = result["scores"]
    subscores = scores["subscores"]
    page = result.get("page", {})
    matrix = result.get("coverage_matrix", [])
    entities_result = result.get("entities", {})
    entities = entities_result.get("entities", {})
    schema = result.get("schema_recommendations", {})
    sourceability = result.get("sourceability", {})
    structure = result.get("structure_audit", {})
    sc_opportunities = result.get("search_console_opportunities", [])
    overall = scores["overall_ai_search_readiness"]
    generated_at = result.get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M"))

    lines = []
    add = lines.append

    add("# AI Search Audit Report")
    add("")
    add(f"**Page:** {page.get('title') or '(untitled)'}  ")
    if page.get("url"):
        add(f"**URL:** {page['url']}  ")
    add(f"**Generated:** {generated_at} · **Tool:** AISO Copilot (free deterministic mode"
        + (", optional LLM enhancement active" if result.get("input", {}).get("llm_active") else "")
        + ")")
    add("")

    add("## Executive Summary")
    add("")
    add(result.get("executive_summary", ""))
    add("")

    add("## AI Search Readiness Score")
    add("")
    add(f"# {overall} / 100 — {_band(overall)}")
    add("")
    add("Estimated readiness of this page to be understood, retrieved, and cited by "
        "AI-assisted search systems. The score is a transparent weighted blend of six "
        "sub-scores (weights below; full formulas in SCORING_RUBRIC.md).")
    add("")

    add("## Subscore Breakdown")
    add("")
    add("| Dimension | Score | Weight | What it measures |")
    add("|-----------|------:|-------:|------------------|")
    for key, weight in result.get("scores", {}).get("weights", {}).items():
        add(f"| {key.replace('_', ' ').title()} | {subscores.get(key, 0)} | "
            f"{int(weight * 100)}% | {_SUBSCORE_MEANING.get(key, '')} |")
    add("")

    add("## Key Strengths")
    add("")
    strengths = (structure.get("strengths", [])[:4]
                 + sourceability.get("strong_evidence", [])[:4])
    if strengths:
        for strength in strengths:
            add(f"- {strength}")
    else:
        add("- No notable strengths detected yet.")
    add("")

    add("## Priority Issues")
    add("")
    actions = result.get("priority_actions", [])
    if actions:
        add("| Priority | Area | Action |")
        add("|----------|------|--------|")
        for action in actions:
            add(f"| {action['priority'].upper()} | {_esc(action['category'])} | {_esc(action['action'])} |")
    else:
        add("No priority issues — the page is in strong shape.")
    add("")

    add("## Query Fan-out Coverage")
    add("")
    covered = [r for r in matrix if r["coverage"] == "Covered"]
    partial = [r for r in matrix if r["coverage"] == "Partial"]
    missing = [r for r in matrix if r["coverage"] == "Missing"]
    add(f"**{scores['subscores']['query_coverage']}/100** — of {len(matrix)} generated "
        f"questions: **{len(covered)} Covered**, **{len(partial)} Partial**, "
        f"**{len(missing)} Missing**. "
        f"(Retrieval method: {result.get('coverage_method', 'deterministic')}.)")
    add("")
    if covered:
        add("**Covered questions:** " + "; ".join(_esc(r["question"]) for r in covered[:12])
            + ("…" if len(covered) > 12 else ""))
        add("")

    add("## Content Gap Matrix")
    add("")
    gaps = partial + missing
    if gaps:
        add("| Question | Intent | Status | Gap | Recommendation |")
        add("|----------|--------|--------|-----|----------------|")
        for row in gaps[:25]:
            add(f"| {_esc(row['question'])} | {row['intent']} | {row['coverage']} | "
                f"{_esc(row.get('gap') or '')} | {_esc(row.get('recommendation') or '')} |")
        if len(gaps) > 25:
            add("")
            add(f"*…and {len(gaps) - 25} more gaps — see the JSON export for the full matrix.*")
    else:
        add("No content gaps detected across the generated question set.")
    add("")

    add("## Sourceability / Citation Readiness")
    add("")
    add(f"**Score: {sourceability.get('sourceability_score', 0)}/100.** This estimates "
        "whether the page contains enough explicit, quotable evidence for an AI system "
        "to use it as a source.")
    add("")
    if sourceability.get("missing_evidence"):
        add("**Missing evidence:**")
        for item in sourceability["missing_evidence"][:8]:
            add(f"- {item}")
        add("")
    if sourceability.get("recommendations"):
        add("**Recommendations:**")
        for rec in sourceability["recommendations"][:6]:
            add(f"- {rec}")
        add("")

    add("## Entity Clarity")
    add("")
    add(f"**Score: {entities_result.get('entity_clarity_score', 0)}/100.**")
    add("")
    add("| Entity type | Detected |")
    add("|-------------|----------|")
    for category in ("brand", "organization", "services", "products", "industries",
                     "locations", "audiences", "problems", "solutions", "benefits",
                     "proof_points", "metrics", "tools"):
        values = entities.get(category, [])
        shown = "; ".join(map(str, values[:3])) if values else "—"
        add(f"| {category.replace('_', ' ').title()} | {_esc(shown)} |")
    add("")
    if entities_result.get("entity_gaps"):
        add("**Gaps:**")
        for gap in entities_result["entity_gaps"][:5]:
            add(f"- {gap}")
        add("")

    add("## Schema Recommendations")
    add("")
    recommended = schema.get("recommended_schema_types", [])
    add(f"**Schema score: {schema.get('schema_score', 0)}/100.** "
        f"Existing types: {', '.join(schema.get('existing_types', [])) or 'none'}. "
        f"Recommended: {', '.join(recommended) or 'none'}."
        + (f" Missing: {', '.join(schema.get('missing_types', []))}." if schema.get("missing_types") else ""))
    add("")
    if schema.get("json_ld_preview"):
        import json as _json

        add("**JSON-LD preview (built only from visible page content):**")
        add("")
        add("```json")
        add(_json.dumps(schema["json_ld_preview"], ensure_ascii=False, indent=2))
        add("```")
        add("")
    for warning in schema.get("warnings", []):
        add(f"> ⚠ {warning}")
    add("")

    add("## Search Console Opportunities")
    add("")
    if sc_opportunities:
        summary = result.get("search_console_summary", {})
        if summary:
            add(f"Analyzed {summary.get('rows', '?')} queries · "
                f"{summary.get('total_impressions', 0):,} impressions · "
                f"average CTR {summary.get('avg_ctr', 0)}%.")
            add("")
        add("| Priority | Query | Type | Position | Impressions | Recommended action |")
        add("|----------|-------|------|---------:|------------:|--------------------|")
        for opp in sc_opportunities[:12]:
            add(f"| {opp['priority'].upper()} | {_esc(opp['query'])} | {opp['opportunity_type']} | "
                f"{opp['position']} | {opp['impressions']:,} | {_esc(opp['recommended_action'])} |")
        if len(sc_opportunities) > 12:
            add("")
            add(f"*…and {len(sc_opportunities) - 12} more — see the JSON export.*")
    else:
        add("No Search Console CSV provided for this run. Upload a performance export "
            "(query, page, clicks, impressions, ctr, position) to add an opportunity analysis.")
    add("")

    add("## n8n Automation Blueprint")
    add("")
    blueprint = result.get("n8n_blueprint", {})
    if blueprint:
        add(f"A reusable automation blueprint (**{blueprint.get('workflow_name', '')}**) was "
            "generated alongside this report:")
        add("")
        add("```text")
        add("  →  ".join(node["name"] for node in blueprint.get("nodes", [])))
        add("```")
        add("")
        add("Files: `outputs/workflows/n8n_workflow_blueprint.md` / `.json` (documentation "
            "only — nothing is connected to a live n8n instance).")
    add("")

    add("## Recommended Action Plan")
    add("")
    if actions:
        for i, action in enumerate(actions, start=1):
            add(f"{i}. **[{action['priority'].upper()}] {action['category']}** — {action['action']}")
    else:
        add("Maintain the current content quality and re-audit after major edits.")
    add("")

    add("## Limitations")
    add("")
    for limitation in result.get("limitations", []):
        add(f"- {limitation}")
    add("")
    add("---")
    add("*Generated by AISO Copilot — a free, deterministic AI Search readiness auditor. "
        "All scores are estimated readiness for human review; no ranking or citation outcome "
        "is guaranteed.*")
    add("")

    return "\n".join(lines)
