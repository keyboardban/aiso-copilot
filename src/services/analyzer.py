"""AISO Copilot core analyzer — the single entry point used by both the
Streamlit UI and the FastAPI backend.

Pipeline (deterministic core, optional LLM polish):

    input → extract → entities → structure audit → fan-out → chunk →
    coverage → sourceability → schema → scores → (search console) →
    n8n blueprint → answer simulations → report files

Every step works with no API key and no network; URL fetching and LLM
enhancement degrade gracefully into the deterministic path.
"""

from datetime import datetime

from src.audit.entity_extractor import extract_entities
from src.audit.schema_recommender import recommend_schema
from src.audit.scoring import compute_scores
from src.audit.sourceability import assess_sourceability
from src.audit.structure_audit import audit_structure
from src.automation.n8n_blueprint_generator import generate_n8n_blueprint, write_blueprint_files
from src.config import (
    ANSWER_SIM_MAX_QUESTIONS,
    MODE_NO_LLM,
    MODE_OPENROUTER,
    OPENROUTER_MODELS,
    PROJECT_NAME,
    _parse_model_list,
    ensure_output_dirs,
)
from src.crawler.extract_content import extract_content
from src.crawler.fetch_page import fetch_page
from src.input.sample_loader import load_sample
from src.input.validators import parse_seed_questions, validate_pasted_content, validate_url
from src.llm.prompt_builder import ANSWER_SYSTEM, POLISH_SYSTEM, build_answer_prompt, build_polish_prompt
from src.llm.provider_base import build_openrouter_agents, get_provider
from src.query.fanout_generator import generate_fanout
from src.reports.json_exporter import export_json
from src.reports.markdown_report import build_executive_summary, build_markdown_report
from src.retrieval.chunker import build_chunks
from src.retrieval.hybrid_coverage import evaluate_coverage
from src.search_console.csv_loader import load_search_console_csv
from src.search_console.opportunity_scoring import find_opportunities
from src.services.metrics import text_metrics
from src.services.session_store import save_run

BASE_LIMITATIONS = [
    "Scores are heuristic, deterministic estimates of readiness — not guarantees of AI search rankings, citations, or AI Overview inclusion.",
    "No live search engine or AI assistant results are scraped or measured; the audit looks only at this page's content.",
    "Coverage is computed against this single page; site-wide authority, off-page mentions, and backlinks are out of scope.",
    "Thai text is matched via character n-grams — a deliberate free approximation, not full word segmentation.",
    "URL fetching does not render JavaScript; for JS-heavy pages, paste the rendered HTML instead.",
    "All recommendations are intended for human review before implementation.",
]


def _error_result(source_type: str, error: str, suggestion: str = "") -> dict:
    return {
        "ok": False,
        "project": PROJECT_NAME,
        "error": error,
        "suggestion": suggestion,
        "input": {"source_type": source_type},
    }


def _derive_topic(user_topic: str, entity_result: dict, page: dict) -> str:
    if user_topic:
        return user_topic
    services = entity_result.get("entities", {}).get("services", [])
    if services:
        return services[0].split("(")[0].strip()
    h1_list = page.get("headings", {}).get("h1", [])
    if h1_list:
        words = h1_list[0].split()
        return " ".join(words[:8])
    return page.get("title", "")[:80]


def _strip_section_prefix(evidence_text: str, section: str) -> str:
    """Evidence text starts with its section heading (and truncation collapses
    newlines), so strip the heading by prefix match."""
    text = (evidence_text or "").strip()
    section = (section or "").strip()
    if section and text.startswith(section):
        text = text[len(section):]
    return " ".join(text.split()).strip()


def _simulate_answers(matrix: list, llm, max_questions: int = ANSWER_SIM_MAX_QUESTIONS) -> list:
    """Feature 13: grounded answer simulations. Template-based by default;
    the first few use the optional LLM when one is active."""
    covered = sorted((r for r in matrix if r["coverage"] == "Covered"),
                     key=lambda r: -r["score"])[:4]
    partial = sorted((r for r in matrix if r["coverage"] == "Partial"),
                     key=lambda r: -r["score"])[:2]
    missing = [r for r in matrix if r["coverage"] == "Missing"][:2]
    selection = (covered + partial + missing)[:max_questions]

    simulations = []
    llm_budget = 4 if (llm and llm.mode != MODE_NO_LLM and llm.available()) else 0

    for row in selection:
        evidence = row.get("evidence", [])
        gap = row.get("gap")
        support = {"Covered": "strong", "Partial": "medium", "Missing": "weak"}[row["coverage"]]

        answer = None
        generator = "template"
        if llm_budget > 0:
            response = llm.complete(
                build_answer_prompt(row["question"], evidence),
                system=ANSWER_SYSTEM, max_tokens=300,
            )
            llm_budget -= 1
            if response:
                missing_note = None
                if "MISSING:" in response:
                    response, _, tail = response.partition("MISSING:")
                    tail = tail.strip()
                    if tail and tail.lower() not in ("nothing", "nothing.", "none", "none."):
                        missing_note = tail
                answer = response.strip()
                generator = llm.mode
                if missing_note and not gap:
                    gap = missing_note

        if answer is None:  # deterministic template path
            if row["coverage"] == "Missing" or not evidence:
                answer = ("The page does not currently provide enough evidence to answer "
                          "this question. An AI assistant would likely skip this page or "
                          "rely on other sources here.")
            else:
                snippets = [_strip_section_prefix(e["text"], e["section"]) for e in evidence[:2]]
                answer = "Based on the page content: " + " ".join(s for s in snippets if s)[:450]
                if row["coverage"] == "Partial" and gap:
                    answer += f" However, coverage is incomplete — {gap.rstrip('.')}."

        simulations.append({
            "question": row["question"],
            "intent": row["intent"],
            "simulated_answer": answer,
            "used_evidence": [{"section": e["section"], "text": e["text"]} for e in evidence],
            "missing_evidence": [gap] if gap else [],
            "support_level": support,
            "generator": generator,
        })
    return simulations


def run_analysis(
    source_type: str,
    url: str = None,
    raw_content: str = None,
    sample_name: str = None,
    target_topic: str = "",
    target_audience: str = "",
    seed_questions=None,
    llm_mode: str = MODE_NO_LLM,
    openrouter_api_key: str = None,
    openrouter_model: str = None,
    ollama_base_url: str = None,
    ollama_model: str = None,
    search_console_source=None,
    write_files: bool = True,
    output_dir=None,
) -> dict:
    """Run the full audit. ``source_type``: url | html | markdown | text | sample.

    Returns the full result object (spec §10 schema plus documented extras).
    On unrecoverable input errors returns {"ok": False, "error", "suggestion"}.
    """
    # --- 1. resolve LLM provider(s) (never required, never fails) ------------
    # openrouter_model may be a single slug, a newline/comma list, or a list.
    if isinstance(openrouter_model, (list, tuple)):
        requested_models = [str(m).strip() for m in openrouter_model if str(m).strip()]
    else:
        requested_models = _parse_model_list(openrouter_model or "")
    models = requested_models or list(OPENROUTER_MODELS)

    # primary single provider drives answer simulation + report polish
    llm, llm_status = get_provider(
        llm_mode, api_key=openrouter_api_key, model=(models[0] if models else None),
        base_url=ollama_base_url, ollama_model=ollama_model,
    )

    # multi-agent fan-out: one provider per free model (only when OpenRouter + key)
    fanout_agents = []
    if llm_mode == MODE_OPENROUTER:
        fanout_agents = build_openrouter_agents(openrouter_api_key, models)
        if len(fanout_agents) > 1:
            names = ", ".join(m.split("/")[-1].replace(":free", "") for m in models)
            llm_status = f"OpenRouter multi-agent mode — {len(fanout_agents)} models: {names}. Errors fall back per-model, then to templates."

    # --- 2. acquire content ---------------------------------------------------
    effective_type = source_type
    input_meta = {"source_type": source_type, "url": None, "sample_name": None}
    if source_type == "sample":
        try:
            sample = load_sample(sample_name or "sample_page.md")
        except FileNotFoundError as exc:
            return _error_result(source_type, str(exc))
        raw, effective_type = sample["content"], sample["source_type"]
        input_meta["sample_name"] = sample["name"]
    elif source_type == "url":
        check = validate_url(url or "")
        if not check["ok"]:
            return _error_result(source_type, check["error"], "Check the URL or use Paste mode.")
        fetched = fetch_page(check["url"])
        if not fetched["ok"]:
            return _error_result(source_type, fetched["error"], fetched["suggestion"] or "")
        raw, effective_type = fetched["html"], "html"
        input_meta["url"] = fetched["final_url"] or check["url"]
    else:  # html | markdown | text
        check = validate_pasted_content(raw_content or "")
        if not check["ok"]:
            return _error_result(source_type, "; ".join(check["issues"]),
                                 "Paste the page HTML, markdown, or text to analyze.")
        raw = check["content"]
        effective_type = source_type if source_type in ("html", "markdown", "text") else "auto"

    # --- 3. deterministic core pipeline ---------------------------------------
    page = extract_content(raw, effective_type, url=input_meta["url"])
    page["readability"] = text_metrics(page["body_text"])

    entity_result = extract_entities(page, target_topic, target_audience)
    structure_result = audit_structure(page, entity_result)

    topic = _derive_topic((target_topic or "").strip(), entity_result, page)
    audience = (target_audience or "").strip() or (
        entity_result["entities"]["audiences"][0]
        if entity_result["entities"]["audiences"] else "businesses"
    )
    if isinstance(seed_questions, str):
        seeds = parse_seed_questions(seed_questions)
    else:
        seeds = [s.strip() for s in (seed_questions or []) if s and s.strip()]

    fanout = generate_fanout(topic, audience, seeds, entity_result["entities"],
                             llm=llm, agents=fanout_agents)
    chunks = build_chunks(page)
    coverage = evaluate_coverage(chunks, fanout["fanout_questions"])
    sourceability_result = assess_sourceability(page, entity_result)
    schema_result = recommend_schema(page, entity_result)
    scores = compute_scores(structure_result, entity_result, coverage,
                            sourceability_result, schema_result,
                            page["technical_extractability"])

    # --- 4. optional Search Console CSV ---------------------------------------
    sc_opportunities, sc_summary = [], {}
    if search_console_source is not None:
        loaded = load_search_console_csv(search_console_source)
        if loaded["ok"]:
            found = find_opportunities(loaded["df"])
            sc_opportunities = found["opportunities"]
            sc_summary = {**loaded["summary"], **found["summary"],
                          "issues": loaded["issues"]}
        else:
            sc_summary = {"error": "; ".join(loaded["issues"])}

    # --- 5. automation blueprint + answer simulations --------------------------
    blueprint = generate_n8n_blueprint()
    simulations = _simulate_answers(coverage["coverage_matrix"], llm)

    # --- 6. assemble the result object (spec §10) ------------------------------
    limitations = list(BASE_LIMITATIONS)
    if llm_mode != MODE_NO_LLM and llm.mode == MODE_NO_LLM:
        limitations.append(f"LLM mode '{llm_mode}' was requested but unavailable — deterministic fallback was used ({llm_status}).")
    for issue in page["technical_extractability"]["issues"]:
        if "truncated" in issue.lower():
            limitations.append(issue)

    result = {
        "ok": True,
        "project": PROJECT_NAME,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "input": {
            "source_type": source_type,
            "url": input_meta["url"],
            "sample_name": input_meta["sample_name"],
            "target_topic": topic,
            "target_audience": audience,
            "llm_mode": llm_mode,
            "llm_active": llm.mode != MODE_NO_LLM,
            "llm_status": llm_status,
            "fanout_note": fanout["llm_note"],
            "fanout_agents": fanout.get("agents_used", []),
        },
        "page": {
            "title": page["title"],
            "meta_description": page["meta_description"],
            "word_count": page["word_count"],
            "headings": page["headings"],
            "sections": page["sections"],
            "links": page["links"],
            "faq_blocks": page["faq_blocks"],
            "json_ld": page["json_ld"],
            "json_ld_types": page["json_ld_types"],
            "readability": page["readability"],
            "extractor": page["extractor"],
            "url": input_meta["url"],
        },
        "scores": {
            "overall_ai_search_readiness": scores["overall_ai_search_readiness"],
            **scores["subscores"],
            "subscores": scores["subscores"],
            "weights": scores["weights"],
        },
        "structure_audit": {
            "strengths": structure_result["strengths"],
            "weaknesses": structure_result["weaknesses"],
            "recommendations": structure_result["recommendations"],
            "checks": structure_result["checks"],
        },
        "query_fanout": fanout["fanout_questions"],
        "seed_questions": fanout["seed_questions"],
        "coverage_matrix": coverage["coverage_matrix"],
        "coverage_method": coverage["method"],
        "sourceability": {
            "score": sourceability_result["sourceability_score"],
            "strong_evidence": sourceability_result["strong_evidence"],
            "missing_evidence": sourceability_result["missing_evidence"],
            "recommendations": sourceability_result["recommendations"],
            "checks": sourceability_result["checks"],
        },
        "entities": entity_result,
        "schema_recommendations": schema_result,
        "search_console_opportunities": sc_opportunities,
        "search_console_summary": sc_summary,
        "n8n_blueprint": blueprint,
        "answer_simulations": simulations,
        "priority_actions": scores["priority_actions"],
        "limitations": limitations,
        "generated_files": [],
    }

    # --- 7. executive summary (template, optionally LLM-polished) --------------
    summary = build_executive_summary(result)
    if llm.mode != MODE_NO_LLM and llm.available():
        polished = llm.complete(build_polish_prompt(summary), system=POLISH_SYSTEM, max_tokens=400)
        if polished:
            summary = polished.strip()
    result["executive_summary"] = summary

    # --- 8. write artifacts -----------------------------------------------------
    if write_files:
        dirs = ensure_output_dirs(output_dir)
        report_md = build_markdown_report(result)
        md_path = dirs["reports"] / "AI_SEARCH_AUDIT_REPORT.md"
        md_path.write_text(report_md, encoding="utf-8")
        json_path = export_json(result, dirs["reports"] / "audit_result.json")
        blueprint_files = write_blueprint_files(blueprint, dirs["workflows"])
        run_path = save_run(
            {k: v for k, v in result.items() if k != "report_markdown"},
            runs_dir=dirs["runs"],
        )
        result["generated_files"] = [str(md_path), str(json_path), *blueprint_files, run_path]
        result["report_markdown"] = report_md
    else:
        result["report_markdown"] = build_markdown_report(result)

    return result


if __name__ == "__main__":  # quick CLI demo: python -m src.services.analyzer
    import argparse
    import json as _json

    parser = argparse.ArgumentParser(description="Run an AISO Copilot audit from the CLI.")
    parser.add_argument("--sample", default="sample_page.md", help="bundled sample page name")
    parser.add_argument("--url", default=None, help="audit a live URL instead of the sample")
    parser.add_argument("--topic", default="", help="target topic")
    parser.add_argument("--audience", default="", help="target audience")
    parser.add_argument("--with-search-console", action="store_true",
                        help="include the bundled Search Console sample CSV")
    args = parser.parse_args()

    from src.input.sample_loader import demo_defaults, sample_search_console_path

    defaults = demo_defaults()
    kwargs = dict(
        target_topic=args.topic or defaults["target_topic"],
        target_audience=args.audience or defaults["target_audience"],
        seed_questions=defaults["seed_questions"],
    )
    if args.with_search_console:
        kwargs["search_console_source"] = sample_search_console_path()

    if args.url:
        outcome = run_analysis("url", url=args.url, **kwargs)
    else:
        outcome = run_analysis("sample", sample_name=args.sample, **kwargs)

    if not outcome.get("ok"):
        print(f"ERROR: {outcome.get('error')}\n{outcome.get('suggestion', '')}")
        raise SystemExit(1)
    print(_json.dumps(outcome["scores"], indent=2))
    print(f"\nLLM: {outcome['input']['llm_status']}")
    print("Generated files:")
    for file_path in outcome["generated_files"]:
        print(f"  - {file_path}")
