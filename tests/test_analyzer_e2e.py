"""End-to-end: the full no-LLM demo pipeline, exactly as the UI runs it."""

import json
from pathlib import Path

import src.llm.provider_base as provider_base
from src.input.sample_loader import demo_defaults, sample_search_console_path
from src.services.analyzer import run_analysis

SPEC_KEYS = {
    "project", "input", "page", "scores", "structure_audit", "query_fanout",
    "coverage_matrix", "sourceability", "entities", "schema_recommendations",
    "search_console_opportunities", "n8n_blueprint", "answer_simulations",
    "priority_actions", "limitations", "generated_files",
}


def test_full_demo_pipeline_no_llm(tmp_path):
    defaults = demo_defaults()
    result = run_analysis(
        "sample",
        sample_name="sample_page.md",
        target_topic=defaults["target_topic"],
        target_audience=defaults["target_audience"],
        seed_questions=defaults["seed_questions"],
        search_console_source=sample_search_console_path(),
        write_files=True,
        output_dir=tmp_path,
    )
    assert result["ok"] is True
    assert SPEC_KEYS <= set(result.keys())

    scores = result["scores"]
    assert 0 <= scores["overall_ai_search_readiness"] <= 100
    for value in scores["subscores"].values():
        assert 0 <= value <= 100

    assert len(result["query_fanout"]) >= 25  # 8 seeds + 20 templates + extras
    assert len(result["coverage_matrix"]) == len(result["query_fanout"])
    statuses = {row["coverage"] for row in result["coverage_matrix"]}
    assert statuses <= {"Covered", "Partial", "Missing"} and len(statuses) >= 2

    assert result["search_console_opportunities"], "sample CSV must yield opportunities"
    assert result["n8n_blueprint"]["nodes"], "blueprint must have nodes"
    assert result["answer_simulations"], "answer simulations expected"

    # files written where asked
    files = [Path(p) for p in result["generated_files"]]
    assert all(f.exists() for f in files)
    report = (tmp_path / "reports" / "AI_SEARCH_AUDIT_REPORT.md").read_text(encoding="utf-8")
    for header in ("# AI Search Audit Report", "## Executive Summary",
                   "## Subscore Breakdown", "## Content Gap Matrix",
                   "## Schema Recommendations", "## Limitations"):
        assert header in report
    audit_json = json.loads((tmp_path / "reports" / "audit_result.json").read_text(encoding="utf-8"))
    assert audit_json["scores"]["overall_ai_search_readiness"] == scores["overall_ai_search_readiness"]
    blueprint = json.loads((tmp_path / "workflows" / "n8n_workflow_blueprint.json").read_text(encoding="utf-8"))
    assert blueprint["workflow_name"]


def test_paste_mode_minimal_text():
    result = run_analysis("text", raw_content="A tiny note about nothing in particular.",
                          write_files=False)
    assert result["ok"] is True
    assert result["scores"]["overall_ai_search_readiness"] < 60  # thin content scores low
    assert result["page"]["word_count"] > 0


def test_invalid_url_fails_gracefully():
    result = run_analysis("url", url="not a url at all")
    assert result["ok"] is False
    assert result["error"]


def test_empty_paste_fails_gracefully():
    result = run_analysis("markdown", raw_content="   ")
    assert result["ok"] is False


def test_openrouter_mode_without_key_does_not_crash(monkeypatch, tmp_path):
    monkeypatch.setattr(provider_base, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(provider_base, "OPENROUTER_MODEL", "")
    result = run_analysis("sample", sample_name="sample_page.md",
                          llm_mode="openrouter", write_files=False)
    assert result["ok"] is True
    assert result["input"]["llm_active"] is False
    assert "fallback" in result["input"]["llm_status"].lower()
    assert any("fallback" in lim.lower() for lim in result["limitations"])


def test_html_sample_pipeline():
    result = run_analysis("sample", sample_name="sample_page.html", write_files=False)
    assert result["ok"] is True
    assert result["page"]["json_ld_types"] == ["Organization"]
    assert result["scores"]["subscores"]["schema"] > 50  # existing markup rewarded
