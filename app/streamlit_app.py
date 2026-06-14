"""AISO Copilot — Streamlit dashboard.

Run from the project root:

    streamlit run app/streamlit_app.py

Free-first: OpenRouter multi-agent mode is the default, but with no API key the
app falls back to deterministic templates — so it always runs free, offline, and
with no billing of any kind.
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
from src.config import (
    MODE_NO_LLM,
    MODE_OLLAMA,
    MODE_OPENROUTER,
    OPENROUTER_API_KEY,
    OPENROUTER_FREE_MODELS_DEFAULT,
    PROJECT_NAME,
    PROJECT_SUBTITLE,
)
from src.input.sample_loader import demo_defaults, list_samples, sample_search_console_path
from src.reports.json_exporter import to_json_string
from src.services.analyzer import run_analysis

try:
    import plotly.graph_objects as go

    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

st.set_page_config(page_title=PROJECT_NAME, layout="wide")

# ---------------------------------------------------------------------------- #
# Visual language: one palette, no emojis, semantic colors only.
# ---------------------------------------------------------------------------- #

# Earthy palette tuned for the Anthropic-inspired cream theme (.streamlit/config.toml)
COLOR = {
    "strong": "#3f7a4e",      # muted green   — >= 80
    "moderate": "#4a6fa5",    # dusty blue    — 60–79
    "developing": "#bf8b2e",  # ochre         — 40–59
    "weak": "#b3402e",        # brick red     — < 40
    "accent": "#bb5a38",      # terracotta (theme primary) for neutral bars
    "muted": "#a8a394",
    "grid": "#dedcd1",
    "text": "#3d3a2a",
}
STATUS_COLOR = {"Covered": COLOR["strong"], "Partial": COLOR["developing"], "Missing": COLOR["weak"]}
PRIORITY_TEXT = {"high": ":red[HIGH]", "medium": ":orange[MEDIUM]", "low": ":green[LOW]"}
SUPPORT_TEXT = {"strong": ":green[Strong support]", "medium": ":orange[Medium support]",
                "weak": ":red[Weak support]"}

# OpenRouter is the default option (first). The audit still runs fully without
# a key — it falls back to deterministic templates automatically.
LLM_MODE_OPTIONS = {
    "OpenRouter — free multi-agent models (default)": MODE_OPENROUTER,
    "No LLM — free deterministic mode": MODE_NO_LLM,
    "Ollama — optional local model": MODE_OLLAMA,
}


def band_color(score: float) -> str:
    if score >= 80:
        return COLOR["strong"]
    if score >= 60:
        return COLOR["moderate"]
    if score >= 40:
        return COLOR["developing"]
    return COLOR["weak"]


def _base_layout(fig, height: int = 300, **kwargs):
    fig.update_layout(
        template="plotly_white",
        height=height,
        margin=dict(l=10, r=10, t=30, b=10),
        font=dict(family="Space Grotesk, -apple-system, Segoe UI, sans-serif",
                  size=13, color=COLOR["text"]),
        paper_bgcolor="rgba(0,0,0,0)",  # blend with the cream theme background
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=kwargs.pop("showlegend", False),
        **kwargs,
    )
    return fig


def gauge_chart(value: int, title: str):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number={"suffix": " / 100", "font": {"size": 36}},
        title={"text": title, "font": {"size": 14, "color": "#6b6753"}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": COLOR["muted"]},
            "bar": {"color": band_color(value), "thickness": 0.28},
            "borderwidth": 0,
            "steps": [
                {"range": [0, 40], "color": "rgba(179, 64, 46, 0.12)"},
                {"range": [40, 60], "color": "rgba(191, 139, 46, 0.12)"},
                {"range": [60, 80], "color": "rgba(74, 111, 165, 0.12)"},
                {"range": [80, 100], "color": "rgba(63, 122, 78, 0.14)"},
            ],
        },
    ))
    return _base_layout(fig, height=260)


def subscore_chart(subscores: dict, weights: dict):
    labels = [f"{k.replace('_', ' ').title()}  ·  {int(weights.get(k, 0) * 100)}% weight"
              for k in subscores]
    values = list(subscores.values())
    fig = go.Figure()
    fig.add_bar(  # light track to 100 behind each bar
        x=[100] * len(values), y=labels, orientation="h",
        marker=dict(color=COLOR["grid"]), hoverinfo="skip", width=0.55,
    )
    fig.add_bar(
        x=values, y=labels, orientation="h",
        marker=dict(color=[band_color(v) for v in values]),
        text=[f"{v}" for v in values], textposition="outside",
        textfont=dict(size=13), width=0.55,
        hovertemplate="%{y}: %{x}/100<extra></extra>",
    )
    fig.update_xaxes(range=[0, 108], showgrid=False, showticklabels=False, zeroline=False)
    fig.update_yaxes(autorange="reversed", ticksuffix="  ")
    return _base_layout(fig, height=290, barmode="overlay")


def coverage_distribution_chart(matrix: list):
    counts = {s: sum(1 for r in matrix if r["coverage"] == s)
              for s in ("Covered", "Partial", "Missing")}
    fig = go.Figure()
    for status, count in counts.items():
        fig.add_bar(
            x=[count], y=["Questions"], orientation="h", name=status,
            marker=dict(color=STATUS_COLOR[status]),
            text=[f"{status}: {count}" if count else ""], textposition="inside",
            insidetextanchor="middle", textfont=dict(color="white", size=13),
            hovertemplate=f"{status}: %{{x}}<extra></extra>",
        )
    fig.update_xaxes(showgrid=False, showticklabels=False, zeroline=False)
    fig.update_yaxes(showticklabels=False)
    return _base_layout(fig, height=110, barmode="stack")


def hbar_chart(series: pd.Series, color=None, height: int = 280, color_map: dict = None):
    series = series.sort_values()
    if color_map:
        color = [color_map.get(str(i), COLOR["moderate"]) for i in series.index]
    fig = go.Figure(go.Bar(
        x=series.values, y=[str(i).replace("_", " ") for i in series.index],
        orientation="h",
        marker=dict(color=color if color is not None else COLOR["accent"]),
        text=series.values, textposition="outside",
        hovertemplate="%{y}: %{x}<extra></extra>",
    ))
    fig.update_xaxes(showgrid=True, gridcolor=COLOR["grid"], zeroline=False,
                     range=[0, float(series.max()) * 1.15])
    return _base_layout(fig, height=height)


def entity_weight_chart(score_breakdown: dict, full_weights: dict):
    """Diverging bar chart: earned categories extend right (green), missed
    categories extend left (red) from a zero baseline. Bar length = how many
    clarity points the category is worth (all-or-nothing per category)."""
    items = sorted(full_weights.items(), key=lambda kv: -kv[1])
    fig = go.Figure()
    for detected, name, color in ((True, "Detected — points earned", COLOR["strong"]),
                                  (False, "Not detected — points missed", COLOR["weak"])):
        group = [(c, w) for c, w in items if bool(score_breakdown.get(c, 0)) == detected]
        if not group:
            continue
        sign = 1 if detected else -1
        fig.add_bar(
            x=[sign * w for _, w in group],
            y=[c.replace("_", " ").title() for c, _ in group],
            orientation="h", width=0.6, name=name,
            marker=dict(color=color),
            text=[f"{'+' if detected else '−'}{w} pts" for _, w in group],
            textposition="outside",
            customdata=[w for _, w in group],
            hovertemplate="%{y}: worth %{customdata} pts — " + name.lower() + "<extra></extra>",
        )
    max_w = max(full_weights.values())
    span = max_w * 1.35
    ticks = [t for t in (-15, -10, -5, 0, 5, 10, 15) if abs(t) <= max_w]
    fig.update_xaxes(
        title_text="← points missed   ·   points earned →",
        range=[-span, span],
        tickvals=ticks, ticktext=[str(abs(t)) for t in ticks],
        showgrid=True, gridcolor=COLOR["grid"],
        zeroline=True, zerolinecolor=COLOR["muted"], zerolinewidth=1.5,
    )
    fig.update_yaxes(categoryorder="array",
                     categoryarray=[c.replace("_", " ").title() for c, _ in items][::-1],
                     ticksuffix="  ")
    return _base_layout(fig, height=380, barmode="relative", showlegend=True,
                        legend=dict(orientation="h", y=1.12))


def sc_scatter_chart(df: pd.DataFrame):
    priority_order = ["high", "medium", "low"]
    color_map = {"high": COLOR["weak"], "medium": COLOR["developing"], "low": COLOR["strong"]}
    fig = go.Figure()
    for priority in priority_order:
        part = df[df["priority"] == priority]
        if part.empty:
            continue
        fig.add_scatter(
            x=part["position"], y=part["ctr"], mode="markers", name=f"{priority} priority",
            marker=dict(
                size=(part["impressions"] ** 0.5).clip(6, 40),
                color=color_map[priority], opacity=0.75,
                line=dict(width=1, color="white"),
            ),
            customdata=part[["query", "impressions", "opportunity_type"]].values,
            hovertemplate=("<b>%{customdata[0]}</b><br>position %{x:.1f} · CTR %{y:.2f}%"
                           "<br>%{customdata[1]:,} impressions · %{customdata[2]}<extra></extra>"),
        )
    fig.update_xaxes(title_text="average position (left = better)", autorange="reversed",
                     showgrid=True, gridcolor=COLOR["grid"])
    fig.update_yaxes(title_text="CTR %", showgrid=True, gridcolor=COLOR["grid"],
                     zeroline=False)
    return _base_layout(fig, height=380, showlegend=True,
                        legend=dict(orientation="h", y=1.08))


def hero_header():
    """Branded page header: oversized title with a terracotta accent."""
    st.markdown(
        f"""
        <div style="padding:0.2rem 0 0.4rem 0">
          <div style="font-size:2.7rem;font-weight:700;letter-spacing:-0.02em;
                      line-height:1.05;color:{COLOR['text']}">
            AISO&nbsp;<span style="color:{COLOR['accent']}">Copilot</span>
          </div>
          <div style="font-size:1.05rem;color:#6b6753;margin-top:0.55rem;max-width:58rem">
            {PROJECT_SUBTITLE}
          </div>
          <div style="height:4px;width:76px;background:{COLOR['accent']};
                      border-radius:2px;margin-top:1rem"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section(title: str, description: str = None):
    """Stand-out section header: terracotta left rule + heavier type."""
    st.markdown(
        f"""
        <div style="display:flex;align-items:baseline;gap:0.6rem;
                    border-left:4px solid {COLOR['accent']};
                    padding-left:0.7rem;margin:1.1rem 0 0.45rem 0">
          <span style="font-size:1.3rem;font-weight:600;letter-spacing:-0.01em;
                       color:{COLOR['text']}">{title}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if description:
        st.caption(description)


def style_status_table(df: pd.DataFrame, status_col: str):
    def colorize(value):
        for status, color in STATUS_COLOR.items():
            if str(value).startswith(status):
                return f"color: {color}; font-weight: 600"
        return ""

    return df.style.map(colorize, subset=[status_col])


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #

def render_sidebar() -> dict:
    st.sidebar.title(PROJECT_NAME)
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
                                 help="Core scoring is always deterministic; LLMs only add extra fan-out questions and polish.")
    params["llm_mode"] = LLM_MODE_OPTIONS[llm_label]
    params["openrouter_model"] = params["openrouter_key"] = None
    params["ollama_url"] = params["ollama_model"] = None
    if params["llm_mode"] == MODE_OPENROUTER:
        env_key = bool(OPENROUTER_API_KEY)
        params["openrouter_key"] = st.sidebar.text_input(
            "OpenRouter API key",
            type="password",
            value="",
            placeholder=("loaded from .env ✓ (leave blank)" if env_key
                         else "sk-or-... — paste your key here"),
            help="Get a free key at openrouter.ai/keys. Leave blank to use OPENROUTER_API_KEY "
                 "from .env. No key = automatic no-LLM fallback (the app still works).",
        )
        params["openrouter_model"] = st.sidebar.text_area(
            "Free models (one per line) — the multi-agent panel",
            value="\n".join(OPENROUTER_FREE_MODELS_DEFAULT),
            height=110,
            help="Each model is queried independently and their questions are merged. "
                 "All defaults are free-tier (':free'). Edit freely; browse current free "
                 "models at openrouter.ai/models (filter: Free). Stale slugs are skipped.",
        )
        key_state = "key from .env" if env_key else "no key yet → will fall back to templates"
        st.sidebar.caption(f"Multi-agent question generation · {key_state}. "
                           "Any quota/auth error falls back per-model, then to deterministic mode.")
    elif params["llm_mode"] == MODE_OLLAMA:
        params["ollama_url"] = st.sidebar.text_input("Ollama base URL", value="http://localhost:11434")
        params["ollama_model"] = st.sidebar.text_input(
            "Ollama model (empty = first installed)", placeholder="e.g. an installed local model"
        )

    st.sidebar.divider()
    params["analyze"] = st.sidebar.button("Analyze AI Search Readiness", type="primary",
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
    st.caption(result["input"]["llm_status"])

    col_gauge, col_bars = st.columns([1, 2])
    with col_gauge:
        if HAS_PLOTLY:
            st.plotly_chart(gauge_chart(scores["overall_ai_search_readiness"],
                                        "Overall AI Search Readiness"),
                            width="stretch", config={"displayModeBar": False})
        else:
            st.metric("Overall AI Search Readiness",
                      f"{scores['overall_ai_search_readiness']} / 100")
        matrix = result["coverage_matrix"]
        covered = sum(1 for r in matrix if r["coverage"] == "Covered")
        m1, m2 = st.columns(2)
        m1.metric("Questions covered", f"{covered} / {len(matrix)}")
        m2.metric("Word count", f"{result['page']['word_count']:,}")
    with col_bars:
        section("Subscores (weighted blend — see SCORING_RUBRIC.md)")
        if HAS_PLOTLY:
            st.plotly_chart(subscore_chart(subscores, scores.get("weights", {})),
                            width="stretch", config={"displayModeBar": False})
        else:
            st.bar_chart(pd.Series(subscores))

    st.divider()
    section("Priority actions")
    actions = result["priority_actions"]
    if actions:
        for action in actions:
            st.markdown(f"{PRIORITY_TEXT[action['priority']]} · **{action['category']}** — {action['action']}")
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
        section("Strengths")
        for strength in audit["strengths"] or ["None detected"]:
            st.markdown(f"- {strength}")
    with col2:
        section("Weaknesses")
        for weakness in audit["weaknesses"] or ["None detected"]:
            st.markdown(f"- {weakness}")

    section("Recommendations")
    for recommendation in audit["recommendations"] or ["No structural changes needed."]:
        st.markdown(f"- {recommendation}")

    st.divider()
    col_meta, col_headings = st.columns(2)
    with col_meta:
        section("Title & meta preview")
        st.markdown(
            f"<div style='border:1px solid #d3d2ca;border-radius:10px;padding:14px;"
            f"background:#ecebe3'>"
            f"<div style='color:#1a0dab;font-size:1.05em'>{page['title'] or '(no title)'}</div>"
            f"<div style='color:#006621;font-size:0.85em'>{page.get('url') or 'example.com'}</div>"
            f"<div style='color:#545454;font-size:0.9em'>{page['meta_description'] or '(no meta description)'}</div>"
            f"</div>", unsafe_allow_html=True)
        st.caption(f"Extractor: {page['extractor']} · Readability: "
                   f"{page['readability'].get('flesch_reading_ease', '—')} Flesch "
                   f"({page['readability'].get('avg_sentence_words', 0)} words/sentence avg)")
    with col_headings:
        section("Extracted headings")
        for level in ("h1", "h2", "h3"):
            for heading in page["headings"].get(level, []):
                indent = {"h1": "", "h2": "&nbsp;&nbsp;&nbsp;", "h3": "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"}[level]
                st.markdown(f"{indent}`{level.upper()}` {heading}", unsafe_allow_html=True)

    with st.expander("All structure checks (weighted)"):
        checks = pd.DataFrame(audit["checks"])[["label", "weight", "passed", "details"]]
        st.dataframe(
            checks, width="stretch", hide_index=True,
            column_config={
                "passed": st.column_config.CheckboxColumn("passed"),
                "weight": st.column_config.NumberColumn("weight", width="small"),
            },
        )


def tab_fanout(result: dict):
    questions = result["query_fanout"]
    section(f"Query Fan-out — {len(questions)} questions")
    st.caption(result["input"].get("fanout_note", ""))
    df = pd.DataFrame(questions)
    col_table, col_chart = st.columns([3, 2])
    with col_table:
        st.dataframe(df, width="stretch", hide_index=True, height=520)
    with col_chart:
        st.markdown("**Intent distribution**")
        if HAS_PLOTLY:
            st.plotly_chart(hbar_chart(df["intent"].value_counts(), height=300),
                            width="stretch", config={"displayModeBar": False})
        else:
            st.bar_chart(df["intent"].value_counts())
        st.markdown("**Question sources**")
        if HAS_PLOTLY:
            st.plotly_chart(hbar_chart(df["source"].value_counts(),
                                       color=COLOR["muted"], height=170),
                            width="stretch", config={"displayModeBar": False})
        else:
            st.bar_chart(df["source"].value_counts())


def tab_coverage(result: dict):
    matrix = result["coverage_matrix"]
    partial = [r for r in matrix if r["coverage"] == "Partial"]
    missing = [r for r in matrix if r["coverage"] == "Missing"]

    col_score, col_dist = st.columns([1, 3])
    with col_score:
        st.metric("Coverage score", f"{result['scores']['subscores']['query_coverage']} / 100")
    with col_dist:
        if HAS_PLOTLY:
            st.plotly_chart(coverage_distribution_chart(matrix), width="stretch",
                            config={"displayModeBar": False})
    st.caption(f"Retrieval method: {result.get('coverage_method', '')} — deterministic, no LLM involved in scoring.")

    rows = pd.DataFrame([{
        "status": r["coverage"],
        "question": r["question"],
        "intent": r["intent"],
        "evidence score": r["score"],
        "evidence sections": ", ".join(sorted({e["section"] for e in r["evidence"]})[:3]),
    } for r in matrix])
    st.dataframe(
        style_status_table(rows, "status"), width="stretch", hide_index=True, height=420,
        column_config={
            "evidence score": st.column_config.ProgressColumn(
                "evidence score", min_value=0.0, max_value=1.0, format="%.2f"),
        },
    )

    st.divider()
    section("Content gaps — evidence & recommendations")
    show = st.radio("Show", ["Partial + Missing", "All questions"], horizontal=True)
    selected = matrix if show == "All questions" else partial + missing
    for row in selected:
        color = STATUS_COLOR[row["coverage"]]
        with st.expander(f"{row['coverage'].upper()} · {row['question']} (score {row['score']})"):
            st.markdown(
                f"<span style='color:{color};font-weight:600'>{row['coverage']}</span> "
                f"· intent: {row['intent']}", unsafe_allow_html=True)
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
    section("Simulated AI answers (from page evidence only)")
    st.caption("How an answer engine might respond using ONLY this page. Template-based in no-LLM mode.")
    for simulation in result["answer_simulations"]:
        with st.expander(f"{simulation['support_level'].title()} support · {simulation['question']}"):
            st.markdown(SUPPORT_TEXT[simulation["support_level"]])
            st.markdown(simulation["simulated_answer"])
            if simulation["missing_evidence"]:
                st.markdown("**Missing evidence:** " + " ".join(simulation["missing_evidence"]))
            st.caption(f"Generator: {simulation['generator']}")


def tab_sourceability(result: dict):
    data = result["sourceability"]
    col_metric, col_chart = st.columns([1, 2])
    with col_metric:
        st.metric("Sourceability / Citation Readiness", f"{data['score']} / 100")
        st.caption("Estimates whether the page has enough explicit, quotable evidence "
                   "for AI systems to use it as a source.")
    with col_chart:
        checks = pd.DataFrame(data["checks"])
        earned = checks[checks["passed"]]["weight"].sum()
        missed = checks[~checks["passed"]]["weight"].sum()
        if HAS_PLOTLY:
            st.plotly_chart(
                hbar_chart(pd.Series({"Evidence present": earned, "Evidence missing": missed}),
                           height=140,
                           color_map={"Evidence present": COLOR["strong"],
                                      "Evidence missing": COLOR["weak"]}),
                width="stretch", config={"displayModeBar": False})
    col1, col2 = st.columns(2)
    with col1:
        section("Strong evidence")
        for item in data["strong_evidence"] or ["None detected"]:
            st.markdown(f"- {item}")
    with col2:
        section("Missing evidence")
        for item in data["missing_evidence"] or ["Nothing missing"]:
            st.markdown(f"- {item}")
    section("Recommendations")
    for recommendation in data["recommendations"] or ["No evidence gaps to fix."]:
        st.markdown(f"- {recommendation}")


def tab_entities(result: dict):
    entity_result = result["entities"]
    entities = entity_result["entities"]
    col_metric, col_chart = st.columns([1, 2])
    with col_metric:
        st.metric("Entity Clarity", f"{entity_result['entity_clarity_score']} / 100")
        st.caption("Weighted presence of the entities AI systems need to disambiguate "
                   "this page (weights in SCORING_RUBRIC.md).")
    with col_chart:
        if HAS_PLOTLY and entity_result.get("score_breakdown"):
            from src.audit.entity_extractor import CLARITY_WEIGHTS

            st.plotly_chart(entity_weight_chart(entity_result["score_breakdown"], CLARITY_WEIGHTS),
                            width="stretch", config={"displayModeBar": False})
            st.caption("Diverging from zero: green bars to the right are points earned "
                       "(category detected on the page); red bars to the left are points "
                       "missed. Bar length = how many of the 100 clarity points the "
                       "category is worth — the longest red bars are your most valuable fixes.")

    rows = [{"entity type": category.replace("_", " ").title(),
             "detected": "; ".join(map(str, values)) if values else "—"}
            for category, values in entities.items()]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=500)
    if entity_result["entity_gaps"]:
        section("Gaps")
        for gap in entity_result["entity_gaps"]:
            st.markdown(f"- {gap}")
    if entity_result["recommendations"]:
        section("Recommendations")
        for recommendation in entity_result["recommendations"]:
            st.markdown(f"- {recommendation}")


def tab_schema(result: dict):
    schema = result["schema_recommendations"]
    col_metric, col_types = st.columns([1, 2])
    with col_metric:
        st.metric("Schema Score", f"{schema['schema_score']} / 100")
    with col_types:
        c1, c2, c3 = st.columns(3)
        c1.markdown("**Existing types**\n\n" + (", ".join(schema["existing_types"]) or "—"))
        c2.markdown("**Recommended**\n\n" + (", ".join(schema["recommended_schema_types"]) or "—"))
        c3.markdown("**Missing**\n\n" + (", ".join(schema["missing_types"]) or "—"))

    section("JSON-LD preview (copy-paste ready)")
    if schema["json_ld_preview"]:
        st.code(json.dumps(schema["json_ld_preview"], ensure_ascii=False, indent=2), language="json")
    else:
        st.info("No schema preview could be built from the visible content.")
    for warning in schema["warnings"]:
        st.warning(warning)
    for note in schema.get("notes", []):
        st.caption(note)
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

    if opportunities:
        df = pd.DataFrame(opportunities)
        section("Opportunity landscape")
        st.caption("Bubble size = impressions. High-priority opportunities cluster where "
                   "impressions are high but CTR underperforms the position.")
        if HAS_PLOTLY:
            st.plotly_chart(sc_scatter_chart(df), width="stretch",
                            config={"displayModeBar": False})

        section(f"Opportunities ({summary.get('total_opportunities', len(opportunities))})")
        table = df[["priority", "query", "opportunity_type", "position", "impressions",
                    "ctr", "reason", "recommended_action"]].copy()

        def colorize_priority(value):
            colors = {"high": COLOR["weak"], "medium": COLOR["developing"], "low": COLOR["strong"]}
            return f"color: {colors.get(value, '')}; font-weight: 600"

        st.dataframe(table.style.map(colorize_priority, subset=["priority"]),
                     width="stretch", hide_index=True, height=420)
        col_chart, _ = st.columns([1, 1])
        with col_chart:
            st.markdown("**By opportunity type**")
            if HAS_PLOTLY:
                st.plotly_chart(hbar_chart(pd.Series(summary.get("by_type", {})),
                                           color=COLOR["muted"], height=200),
                                width="stretch", config={"displayModeBar": False})
            else:
                st.bar_chart(pd.Series(summary.get("by_type", {})))
    else:
        st.success("No opportunity patterns matched — solid performance across these queries.")


def tab_n8n(result: dict):
    blueprint = result["n8n_blueprint"]
    section(f"{blueprint['workflow_name']}")
    st.caption("Blueprint only — generated as documentation, never connected to a live n8n instance.")
    st.code("  ->  ".join(node["name"] for node in blueprint["nodes"]), language="text")
    st.dataframe(pd.DataFrame(blueprint["nodes"]), width="stretch", hide_index=True)
    for note in blueprint["notes"]:
        st.markdown(f"- {note}")
    with st.expander("Blueprint JSON (incl. n8n import skeleton)"):
        st.json(blueprint)


def tab_report(result: dict):
    section("Client-ready audit report")
    report_md = result.get("report_markdown", "")
    blueprint = result["n8n_blueprint"]
    col1, col2, col3, col4 = st.columns(4)
    col1.download_button("Download report (.md)", report_md,
                         file_name="AI_SEARCH_AUDIT_REPORT.md", width="stretch")
    col2.download_button("Download result (.json)",
                         to_json_string({k: v for k, v in result.items() if k != "report_markdown"}),
                         file_name="audit_result.json", width="stretch")
    col3.download_button("n8n blueprint (.md)", blueprint_markdown(blueprint),
                         file_name="n8n_workflow_blueprint.md", width="stretch")
    col4.download_button("n8n blueprint (.json)",
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

    hero_header()

    if params["analyze"]:
        with st.spinner("Running the deterministic audit pipeline…"):
            st.session_state["result"] = execute_analysis(params)

    result = st.session_state.get("result")
    if result is None:
        st.markdown("""
**Audit how ready a webpage is to be understood, retrieved, and cited by AI-assisted search.**

| Capability | What you get |
|---|---|
| Query fan-out coverage | Generates the question set an AI assistant would explore, then checks which ones your content can answer — with evidence. |
| Sourceability score | Do you have quotable definitions, steps, numbers, and proof points? |
| Entity clarity | Brand, services, audience, market — named clearly enough for machines? |
| Schema recommendations | JSON-LD preview built strictly from your visible content. |
| Search Console opportunities | Optional CSV upload → prioritized AI-search content opportunities. |
| Client-ready report | Markdown + JSON export, plus an n8n automation blueprint. |

**Try it now:** keep *Sample Demo* selected in the sidebar and click **Analyze AI Search
Readiness** — it runs fully offline with zero API keys.

> Core analysis = local + free + deterministic · Optional LLM = OpenRouter free model or local Ollama · Fallback = rule-based templates
""")
        return

    if not result.get("ok"):
        st.error(f"**Could not analyze:** {result.get('error')}")
        if result.get("suggestion"):
            st.info(result["suggestion"])
        return

    tabs = st.tabs([
        "Overview", "Structure Audit", "Query Fan-out", "Coverage Matrix",
        "Sourceability", "Entities", "Schema", "Search Console",
        "n8n Blueprint", "Report", "Raw JSON",
    ])
    renderers = [tab_overview, tab_structure, tab_fanout, tab_coverage,
                 tab_sourceability, tab_entities, tab_schema, tab_search_console,
                 tab_n8n, tab_report, tab_raw_json]
    for tab, renderer in zip(tabs, renderers):
        with tab:
            renderer(result)


if __name__ == "__main__":
    main()
