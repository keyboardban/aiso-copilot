"""AISO Copilot — Streamlit dashboard.

Run from the project root:

    streamlit run app/streamlit_app.py

Free-first: the default flow (Sample Demo + No-LLM mode) needs no API key,
no internet, and no billing of any kind.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from src.automation.n8n_blueprint_generator import blueprint_markdown
from src.config import MODE_NO_LLM, MODE_OLLAMA, MODE_OPENROUTER, PROJECT_NAME, PROJECT_SUBTITLE
from src.input.sample_loader import demo_defaults, list_samples, sample_search_console_path
from src.reports.json_exporter import to_json_string
from src.services.analyzer import run_analysis

try:
    import plotly.graph_objects as go

    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

st.set_page_config(page_title=PROJECT_NAME, page_icon="🔎", layout="wide")

COVERAGE_BADGE = {"Covered": "✅ Covered", "Partial": "🟡 Partial", "Missing": "🔴 Missing"}
PRIORITY_BADGE = {"high": "🔴 HIGH", "medium": "🟡 MEDIUM", "low": "🟢 LOW"}

LLM_MODE_OPTIONS = {
    "No LLM — free deterministic mode (default)": MODE_NO_LLM,
    "OpenRouter — optional free model (your slug)": MODE_OPENROUTER,
    "Ollama — optional local model": MODE_OLLAMA,
}


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #

def render_sidebar() -> dict:
    st.sidebar.title(f"🔎 {PROJECT_NAME}")
    st.sidebar.caption("Free AI Search Visibility Auditor — no paid APIs, no billing, ever.")

    input_mode = st.sidebar.radio(
        "Input mode",
        ["Sample Demo", "Paste HTML / Markdown / Text", "URL"],
        help="Sample Demo works fully offline. URL fetching is best-effort; paste mode always works.",
    )

    params = {"input_mode": input_mode}
    defaults = demo_defaults()
    is_demo = input_mode == "Sample Demo"

    if input_mode == "URL":
        params["url"] = st.sidebar.text_input("Page URL", placeholder="https://example.com/services/…")
    elif input_mode == "Paste HTML / Markdown / Text":
        params["paste_format"] = st.sidebar.selectbox(
            "Pasted format", ["Auto-detect", "HTML", "Markdown", "Plain text"]
        )
        params["pasted"] = st.sidebar.text_area(
            "Paste page content", height=180,
            placeholder="Paste the page HTML (View Source), markdown, or plain text…",
        )
    else:
        samples = list_samples() or ["sample_page.md"]
        params["sample_name"] = st.sidebar.selectbox("Sample page", samples)

    st.sidebar.divider()
    params["topic"] = st.sidebar.text_input(
        "Target topic", value=defaults["target_topic"] if is_demo else "",
        placeholder="e.g. AI Search Optimization",
    )
    params["audience"] = st.sidebar.text_input(
        "Target audience", value=defaults["target_audience"] if is_demo else "",
        placeholder="e.g. Thai businesses",
    )
    params["seeds"] = st.sidebar.text_area(
        "Seed questions (one per line)",
        value="\n".join(defaults["seed_questions"]) if is_demo else "",
        height=130,
    )

    st.sidebar.divider()
    st.sidebar.markdown("**Search Console (optional)**")
    params["sc_upload"] = st.sidebar.file_uploader(
        "Upload performance CSV", type=["csv"],
        help="Columns: query, page, clicks, impressions, ctr, position. CSV only — no API, no OAuth.",
    )
    params["sc_use_sample"] = st.sidebar.checkbox(
        "Use bundled sample CSV", value=is_demo and params["sc_upload"] is None,
    )

    st.sidebar.divider()
    llm_label = st.sidebar.radio("LLM mode", list(LLM_MODE_OPTIONS.keys()),
                                 help="The audit is fully deterministic; LLMs only add optional polish.")
    params["llm_mode"] = LLM_MODE_OPTIONS[llm_label]
    params["openrouter_model"] = params["openrouter_key"] = None
    params["ollama_url"] = params["ollama_model"] = None
    if params["llm_mode"] == MODE_OPENROUTER:
        params["openrouter_model"] = st.sidebar.text_input(
            "OpenRouter model slug (pick a FREE model)",
            placeholder="e.g. a ':free' slug from openrouter.ai/models",
            help="You choose the model. Nothing is hardcoded; free-tier slugs end in ':free'.",
        )
        params["openrouter_key"] = st.sidebar.text_input(
            "OpenRouter API key", type="password",
            help="Leave empty to use OPENROUTER_API_KEY from .env. Missing key = automatic no-LLM fallback.",
        )
        st.sidebar.caption("⚠ Optional. Any quota/auth/provider error falls back to deterministic mode.")
    elif params["llm_mode"] == MODE_OLLAMA:
        params["ollama_url"] = st.sidebar.text_input("Ollama base URL", value="http://localhost:11434")
        params["ollama_model"] = st.sidebar.text_input(
            "Ollama model (empty = first installed)", placeholder="e.g. an installed local model"
        )

    st.sidebar.divider()
    params["analyze"] = st.sidebar.button("🚀 Analyze AI Search Readiness", type="primary",
                                          width="stretch")
    st.sidebar.caption("Core analysis is local & deterministic — runs with zero API keys.")
    return params


def execute_analysis(params: dict):
    if params["sc_upload"] is not None:
        sc_source = params["sc_upload"]
    elif params["sc_use_sample"]:
        sc_source = sample_search_console_path()
    else:
        sc_source = None

    kwargs = dict(
        target_topic=params["topic"],
        target_audience=params["audience"],
        seed_questions=params["seeds"],
        llm_mode=params["llm_mode"],
        openrouter_api_key=params["openrouter_key"],
        openrouter_model=params["openrouter_model"],
        ollama_base_url=params["ollama_url"],
        ollama_model=params["ollama_model"],
        search_console_source=sc_source,
    )
    if params["input_mode"] == "URL":
        return run_analysis("url", url=params.get("url", ""), **kwargs)
    if params["input_mode"] == "Paste HTML / Markdown / Text":
        format_map = {"Auto-detect": "auto", "HTML": "html",
                      "Markdown": "markdown", "Plain text": "text"}
        return run_analysis(format_map[params["paste_format"]],
                            raw_content=params.get("pasted", ""), **kwargs)
    return run_analysis("sample", sample_name=params.get("sample_name"), **kwargs)


# --------------------------------------------------------------------------- #
# Tabs
# --------------------------------------------------------------------------- #

def tab_overview(result: dict):
    scores = result["scores"]
    subscores = scores["subscores"]
    st.subheader("AI Search Readiness")
    st.caption(result["input"]["llm_status"])

    col_main, col_radar = st.columns([1, 2])
    with col_main:
        st.metric("Overall AI Search Readiness", f"{scores['overall_ai_search_readiness']} / 100")
        matrix = result["coverage_matrix"]
        covered = sum(1 for r in matrix if r["coverage"] == "Covered")
        st.metric("Query Fan-out Coverage", f"{covered} / {len(matrix)} covered")
        st.metric("Page word count", f"{result['page']['word_count']:,}")
    with col_radar:
        labels = [k.replace("_", " ").title() for k in subscores]
        values = list(subscores.values())
        if HAS_PLOTLY:
            fig = go.Figure(go.Scatterpolar(
                r=values + values[:1], theta=labels + labels[:1],
                fill="toself", name="Subscores",
            ))
            fig.update_layout(polar=dict(radialaxis=dict(range=[0, 100])),
                              height=320, margin=dict(l=60, r=60, t=30, b=30),
                              showlegend=False)
            st.plotly_chart(fig, width="stretch")
        else:
            st.bar_chart(pd.DataFrame({"score": values}, index=labels))

    columns = st.columns(6)
    for col, (key, value) in zip(columns, subscores.items()):
        col.metric(key.replace("_", " ").title(), value)

    st.divider()
    st.subheader("Priority actions")
    actions = result["priority_actions"]
    if actions:
        for action in actions:
            st.markdown(f"{PRIORITY_BADGE[action['priority']]} · **{action['category']}** — {action['action']}")
    else:
        st.success("No priority issues found.")

    with st.expander("Executive summary"):
        st.markdown(result.get("executive_summary", ""))
    with st.expander("Limitations (please read)"):
        for limitation in result["limitations"]:
            st.markdown(f"- {limitation}")


def tab_structure(result: dict):
    audit = result["structure_audit"]
    page = result["page"]
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("✅ Strengths")
        for strength in audit["strengths"] or ["None detected"]:
            st.markdown(f"- {strength}")
    with col2:
        st.subheader("⚠ Weaknesses")
        for weakness in audit["weaknesses"] or ["None detected"]:
            st.markdown(f"- {weakness}")

    st.subheader("Recommendations")
    for recommendation in audit["recommendations"] or ["No structural changes needed."]:
        st.markdown(f"- {recommendation}")

    st.divider()
    col_meta, col_headings = st.columns(2)
    with col_meta:
        st.subheader("Title & meta preview")
        st.markdown(
            f"<div style='border:1px solid #ddd;border-radius:8px;padding:12px'>"
            f"<div style='color:#1a0dab;font-size:1.05em'>{page['title'] or '(no title)'}</div>"
            f"<div style='color:#006621;font-size:0.85em'>{page.get('url') or 'example.com'}</div>"
            f"<div style='color:#545454;font-size:0.9em'>{page['meta_description'] or '(no meta description)'}</div>"
            f"</div>", unsafe_allow_html=True)
        st.caption(f"Extractor: {page['extractor']} · Readability: "
                   f"{page['readability'].get('flesch_reading_ease', '—')} Flesch "
                   f"({page['readability'].get('avg_sentence_words', 0)} words/sentence avg)")
    with col_headings:
        st.subheader("Extracted headings")
        for level in ("h1", "h2", "h3"):
            for heading in page["headings"].get(level, []):
                indent = {"h1": "", "h2": "&nbsp;&nbsp;&nbsp;", "h3": "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"}[level]
                st.markdown(f"{indent}**{level.upper()}** · {heading}", unsafe_allow_html=True)

    with st.expander("All structure checks (weighted)"):
        st.dataframe(pd.DataFrame(audit["checks"])[["label", "weight", "passed", "details"]],
                     width="stretch", hide_index=True)


def tab_fanout(result: dict):
    questions = result["query_fanout"]
    st.subheader(f"Query Fan-out — {len(questions)} questions")
    st.caption(result["input"].get("fanout_note", ""))
    df = pd.DataFrame(questions)
    counts = df["intent"].value_counts()
    col_table, col_chart = st.columns([2, 1])
    with col_table:
        st.dataframe(df, width="stretch", hide_index=True, height=480)
    with col_chart:
        st.markdown("**Intent distribution**")
        st.bar_chart(counts)
        st.markdown("**Sources**")
        st.bar_chart(df["source"].value_counts())


def tab_coverage(result: dict):
    matrix = result["coverage_matrix"]
    covered = [r for r in matrix if r["coverage"] == "Covered"]
    partial = [r for r in matrix if r["coverage"] == "Partial"]
    missing = [r for r in matrix if r["coverage"] == "Missing"]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Coverage score", f"{result['scores']['subscores']['query_coverage']} / 100")
    col2.metric("✅ Covered", len(covered))
    col3.metric("🟡 Partial", len(partial))
    col4.metric("🔴 Missing", len(missing))
    st.caption(f"Retrieval method: {result.get('coverage_method', '')} — deterministic, no LLM involved in scoring.")

    rows = [{
        "status": COVERAGE_BADGE[r["coverage"]],
        "question": r["question"],
        "intent": r["intent"],
        "score": r["score"],
        "evidence_sections": ", ".join(sorted({e["section"] for e in r["evidence"]})[:3]),
    } for r in matrix]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=420)

    st.divider()
    st.subheader("Content gaps — evidence & recommendations")
    show = st.radio("Show", ["Partial + Missing", "All questions"], horizontal=True)
    selected = matrix if show == "All questions" else partial + missing
    for row in selected:
        with st.expander(f"{COVERAGE_BADGE[row['coverage']]} · {row['question']} (score {row['score']})"):
            if row.get("gap"):
                st.markdown(f"**Gap:** {row['gap']}")
            if row.get("recommendation"):
                st.markdown(f"**Recommendation:** {row['recommendation']}")
            if row["evidence"]:
                st.markdown("**Best evidence found:**")
                for evidence in row["evidence"]:
                    st.markdown(f"> *{evidence['section']}* (match {evidence['score']}): {evidence['text']}")
            else:
                st.markdown("*No relevant evidence found on the page.*")

    st.divider()
    st.subheader("Simulated AI answers (from page evidence only)")
    st.caption("How an answer engine might respond using ONLY this page. Template-based in no-LLM mode.")
    for simulation in result["answer_simulations"]:
        badge = {"strong": "✅ strong", "medium": "🟡 medium", "weak": "🔴 weak"}[simulation["support_level"]]
        with st.expander(f"{badge} support · {simulation['question']}"):
            st.markdown(simulation["simulated_answer"])
            if simulation["missing_evidence"]:
                st.markdown("**Missing evidence:** " + " ".join(simulation["missing_evidence"]))
            st.caption(f"Generator: {simulation['generator']}")


def tab_sourceability(result: dict):
    data = result["sourceability"]
    st.metric("Sourceability / Citation Readiness", f"{data['score']} / 100")
    st.caption("Estimates whether the page has enough explicit, quotable evidence for AI systems to use it as a source.")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("✅ Strong evidence")
        for item in data["strong_evidence"] or ["None detected"]:
            st.markdown(f"- {item}")
    with col2:
        st.subheader("🔴 Missing evidence")
        for item in data["missing_evidence"] or ["Nothing missing"]:
            st.markdown(f"- {item}")
    st.subheader("Recommendations")
    for recommendation in data["recommendations"] or ["No evidence gaps to fix."]:
        st.markdown(f"- {recommendation}")


def tab_entities(result: dict):
    entity_result = result["entities"]
    entities = entity_result["entities"]
    st.metric("Entity Clarity", f"{entity_result['entity_clarity_score']} / 100")
    rows = [{"entity type": category.replace("_", " ").title(),
             "detected": "; ".join(map(str, values)) if values else "—",
             "weight": entity_result["score_breakdown"].get(category, 0)}
            for category, values in entities.items()]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=500)
    if entity_result["entity_gaps"]:
        st.subheader("Gaps")
        for gap in entity_result["entity_gaps"]:
            st.markdown(f"- {gap}")
    if entity_result["recommendations"]:
        st.subheader("Recommendations")
        for recommendation in entity_result["recommendations"]:
            st.markdown(f"- {recommendation}")


def tab_schema(result: dict):
    schema = result["schema_recommendations"]
    st.metric("Schema Score", f"{schema['schema_score']} / 100")
    col1, col2, col3 = st.columns(3)
    col1.markdown("**Existing types**\n\n" + (", ".join(schema["existing_types"]) or "—"))
    col2.markdown("**Recommended types**\n\n" + (", ".join(schema["recommended_schema_types"]) or "—"))
    col3.markdown("**Missing types**\n\n" + (", ".join(schema["missing_types"]) or "—"))

    st.subheader("JSON-LD preview (copy-paste ready)")
    if schema["json_ld_preview"]:
        st.code(json.dumps(schema["json_ld_preview"], ensure_ascii=False, indent=2), language="json")
    else:
        st.info("No schema preview could be built from the visible content.")
    for warning in schema["warnings"]:
        st.warning(warning)
    for note in schema.get("notes", []):
        st.caption(f"ℹ {note}")
    with st.expander("Score breakdown"):
        st.json(schema.get("score_parts", {}))


def tab_search_console(result: dict):
    summary = result.get("search_console_summary", {})
    opportunities = result.get("search_console_opportunities", [])
    if not summary and not opportunities:
        st.info("No Search Console data for this run. Upload a performance CSV in the sidebar "
                "(or tick 'Use bundled sample CSV') and re-analyze. CSV only — no API or billing.")
        return
    if summary.get("error"):
        st.error(f"CSV problem: {summary['error']}")
        return

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Queries", summary.get("rows", 0))
    col2.metric("Clicks", f"{summary.get('total_clicks', 0):,}")
    col3.metric("Impressions", f"{summary.get('total_impressions', 0):,}")
    col4.metric("Avg CTR", f"{summary.get('avg_ctr', 0)}%")
    col5.metric("Avg position", summary.get("avg_position_weighted", 0))

    st.subheader(f"Opportunities ({summary.get('total_opportunities', len(opportunities))})")
    if opportunities:
        df = pd.DataFrame(opportunities)
        df["priority"] = df["priority"].map(PRIORITY_BADGE)
        st.dataframe(
            df[["priority", "query", "opportunity_type", "position", "impressions", "ctr",
                "reason", "recommended_action"]],
            width="stretch", hide_index=True, height=420,
        )
        st.markdown("**By opportunity type**")
        st.bar_chart(pd.Series(summary.get("by_type", {})))
    else:
        st.success("No opportunity patterns matched — solid performance across these queries.")


def tab_n8n(result: dict):
    blueprint = result["n8n_blueprint"]
    st.subheader(blueprint["workflow_name"])
    st.caption("Blueprint only — generated as documentation, never connected to a live n8n instance.")
    st.code("  →  ".join(node["name"] for node in blueprint["nodes"]), language="text")
    st.dataframe(pd.DataFrame(blueprint["nodes"]), width="stretch", hide_index=True)
    for note in blueprint["notes"]:
        st.markdown(f"- {note}")
    with st.expander("Blueprint JSON (incl. n8n import skeleton)"):
        st.json(blueprint)


def tab_report(result: dict):
    st.subheader("Client-ready audit report")
    report_md = result.get("report_markdown", "")
    blueprint = result["n8n_blueprint"]
    col1, col2, col3, col4 = st.columns(4)
    col1.download_button("⬇ Report (.md)", report_md,
                         file_name="AI_SEARCH_AUDIT_REPORT.md", width="stretch")
    col2.download_button("⬇ Full result (.json)",
                         to_json_string({k: v for k, v in result.items() if k != "report_markdown"}),
                         file_name="audit_result.json", width="stretch")
    col3.download_button("⬇ n8n blueprint (.md)", blueprint_markdown(blueprint),
                         file_name="n8n_workflow_blueprint.md", width="stretch")
    col4.download_button("⬇ n8n blueprint (.json)",
                         json.dumps(blueprint, ensure_ascii=False, indent=2),
                         file_name="n8n_workflow_blueprint.json", width="stretch")
    if result.get("generated_files"):
        st.caption("Also written to disk: " + " · ".join(f"`{f}`" for f in result["generated_files"]))
    st.divider()
    st.markdown(report_md)


def tab_raw_json(result: dict):
    st.caption("The complete analysis object (report markdown omitted for readability).")
    st.json({k: v for k, v in result.items() if k != "report_markdown"})


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    params = render_sidebar()

    st.title(f"🔎 {PROJECT_NAME}")
    st.caption(PROJECT_SUBTITLE)

    if params["analyze"]:
        with st.spinner("Running the deterministic audit pipeline…"):
            st.session_state["result"] = execute_analysis(params)

    result = st.session_state.get("result")
    if result is None:
        st.markdown("""
**Audit how ready a webpage is to be understood, retrieved, and cited by AI-assisted search.**

| | |
|---|---|
| 🧩 **Query fan-out coverage** | Generates the question set an AI assistant would explore, then checks which ones your content can answer — with evidence. |
| 📌 **Sourceability score** | Do you have quotable definitions, steps, numbers, and proof points? |
| 🏷 **Entity clarity** | Brand, services, audience, market — named clearly enough for machines? |
| 🧱 **Schema recommendations** | JSON-LD preview built strictly from your visible content. |
| 📈 **Search Console opportunities** | Optional CSV upload → AI-search content opportunities. |
| 📄 **Client-ready report** | Markdown + JSON export, plus an n8n automation blueprint. |

**Try it now:** keep *Sample Demo* selected in the sidebar and hit **🚀 Analyze** —
it runs fully offline with zero API keys.

> Core analysis = local + free + deterministic · Optional LLM = OpenRouter free model or local Ollama · Fallback = rule-based templates
""")
        return

    if not result.get("ok"):
        st.error(f"**Could not analyze:** {result.get('error')}")
        if result.get("suggestion"):
            st.info(result["suggestion"])
        return

    tabs = st.tabs([
        "📊 Overview", "🧱 Structure Audit", "🧩 Query Fan-out", "🗺 Coverage Matrix",
        "📌 Sourceability", "🏷 Entities", "🧬 Schema", "📈 Search Console",
        "⚙️ n8n Blueprint", "📄 Report", "🧾 Raw JSON",
    ])
    renderers = [tab_overview, tab_structure, tab_fanout, tab_coverage,
                 tab_sourceability, tab_entities, tab_schema, tab_search_console,
                 tab_n8n, tab_report, tab_raw_json]
    for tab, renderer in zip(tabs, renderers):
        with tab:
            renderer(result)


if __name__ == "__main__":
    main()
