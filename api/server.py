"""Optional FastAPI backend for AISO Copilot.

Same analyzer as the Streamlit UI, exposed as JSON endpoints (useful for the
n8n blueprint's HTTP node). Run with:

    uvicorn api.server:app --reload --port 8000

Entirely optional — the Streamlit app never requires this server.
"""

import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.audit.entity_extractor import extract_entities
from src.audit.schema_recommender import recommend_schema
from src.config import MODE_NO_LLM, PROJECT_NAME, PROJECT_SUBTITLE
from src.crawler.extract_content import extract_content
from src.llm.provider_base import get_provider
from src.query.fanout_generator import generate_fanout
from src.query.templates import classify_intent
from src.reports.markdown_report import build_executive_summary, build_markdown_report
from src.retrieval.chunker import build_chunks
from src.retrieval.hybrid_coverage import evaluate_coverage
from src.services.analyzer import run_analysis

app = FastAPI(
    title=PROJECT_NAME,
    description=PROJECT_SUBTITLE,
    version="1.0.0",
)


class AnalyzeRequest(BaseModel):
    source_type: str = Field("markdown", description="url | html | markdown | text | sample")
    url: Optional[str] = None
    content: Optional[str] = None
    sample_name: Optional[str] = None
    target_topic: str = ""
    target_audience: str = ""
    seed_questions: List[str] = []
    llm_mode: str = MODE_NO_LLM
    openrouter_api_key: Optional[str] = None
    openrouter_model: Optional[str] = None
    write_files: bool = False


class FanoutRequest(BaseModel):
    topic: str
    audience: str = ""
    seed_questions: List[str] = []
    llm_mode: str = MODE_NO_LLM
    openrouter_api_key: Optional[str] = None
    openrouter_model: Optional[str] = None


class CoverageRequest(BaseModel):
    content: str
    source_type: str = "auto"
    questions: List[str]


class SchemaRequest(BaseModel):
    content: str
    source_type: str = "auto"
    url: Optional[str] = None


class ReportRequest(BaseModel):
    analysis: dict


@app.get("/health")
def health():
    return {"status": "ok", "project": PROJECT_NAME, "default_llm_mode": MODE_NO_LLM}


@app.post("/analyze")
def analyze(request: AnalyzeRequest):
    result = run_analysis(
        source_type=request.source_type,
        url=request.url,
        raw_content=request.content,
        sample_name=request.sample_name,
        target_topic=request.target_topic,
        target_audience=request.target_audience,
        seed_questions=request.seed_questions,
        llm_mode=request.llm_mode,
        openrouter_api_key=request.openrouter_api_key,
        openrouter_model=request.openrouter_model,
        write_files=request.write_files,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=422, detail={
            "error": result.get("error"), "suggestion": result.get("suggestion"),
        })
    return result


@app.post("/fanout")
def fanout(request: FanoutRequest):
    llm, llm_status = get_provider(
        request.llm_mode,
        api_key=request.openrouter_api_key,
        model=request.openrouter_model,
    )
    generated = generate_fanout(request.topic, request.audience,
                                request.seed_questions, llm=llm)
    generated["llm_status"] = llm_status
    return generated


@app.post("/coverage")
def coverage(request: CoverageRequest):
    if not request.questions:
        raise HTTPException(status_code=422, detail="Provide at least one question.")
    page = extract_content(request.content, request.source_type)
    chunks = build_chunks(page)
    questions = [
        {"question": q, "intent": classify_intent(q), "source": "user"}
        for q in request.questions if q.strip()
    ]
    return evaluate_coverage(chunks, questions)


@app.post("/schema/recommend")
def schema_recommend(request: SchemaRequest):
    page = extract_content(request.content, request.source_type, url=request.url)
    entities = extract_entities(page)
    return recommend_schema(page, entities)


@app.post("/report/generate")
def report_generate(request: ReportRequest):
    analysis = request.analysis
    try:
        if "executive_summary" not in analysis:
            analysis["executive_summary"] = build_executive_summary(analysis)
        markdown = build_markdown_report(analysis)
    except (KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Analysis object missing expected fields ({exc}); pass the full /analyze result.",
        )
    return {"report_markdown": markdown}
