"""Coverage classification must be deterministic and LLM-free."""

from src.crawler.extract_content import extract_content
from src.retrieval.chunker import build_chunks
from src.retrieval.hybrid_coverage import evaluate_coverage

PAGE = """
# Solar Panel Installation Services

## What is solar panel installation?

Solar panel installation is the process of mounting photovoltaic panels on a
roof and connecting them to an inverter so a building can generate its own
electricity. A typical residential installation takes two to three days.

## Our installation process

1. Site survey and roof assessment
2. System design and permit application
3. Panel mounting and electrical connection
4. Inspection and grid activation

## Pricing

A typical home system costs between 150,000 and 300,000 THB depending on
capacity, with most customers breaking even within seven years.
"""


def _matrix(questions):
    page = extract_content(PAGE, "markdown")
    chunks = build_chunks(page)
    items = [{"question": q, "intent": "definition", "source": "template"} for q in questions]
    return evaluate_coverage(chunks, items)


def test_covered_partial_missing_classification():
    result = _matrix([
        "What is solar panel installation?",          # directly answered
        "How much does solar panel installation cost?",  # pricing section exists
        "What is quantum basket weaving on Mars?",     # nonsense — nothing relevant
    ])
    rows = {r["question"]: r for r in result["coverage_matrix"]}

    direct = rows["What is solar panel installation?"]
    assert direct["coverage"] == "Covered"
    assert direct["evidence"], "covered questions must carry evidence"
    assert direct["gap"] is None

    nonsense = rows["What is quantum basket weaving on Mars?"]
    assert nonsense["coverage"] == "Missing"
    assert nonsense["recommendation"]

    cost = rows["How much does solar panel installation cost?"]
    assert cost["coverage"] in ("Covered", "Partial")


def test_scores_are_bounded():
    result = _matrix(["What is solar panel installation?", "Totally unrelated zebra question?"])
    assert 0 <= result["coverage_score"] <= 100
    for row in result["coverage_matrix"]:
        assert 0.0 <= row["score"] <= 1.0
        for evidence in row["evidence"]:
            assert set(evidence) >= {"section", "text", "score"}


def test_empty_content_yields_missing():
    result = evaluate_coverage([], [{"question": "What is X?", "intent": "definition", "source": "template"}])
    row = result["coverage_matrix"][0]
    assert row["coverage"] == "Missing"
    assert result["coverage_score"] == 0


def test_thai_question_matches_thai_content():
    page = extract_content(
        "# บริการของเรา\n\nบริการติดตั้งโซลาร์เซลล์สำหรับบ้านและธุรกิจ "
        "พร้อมการรับประกันสิบปีและทีมวิศวกรมืออาชีพ", "markdown")
    chunks = build_chunks(page)
    result = evaluate_coverage(chunks, [
        {"question": "บริการติดตั้งโซลาร์เซลล์", "intent": "commercial", "source": "seed"},
    ])
    assert result["coverage_matrix"][0]["score"] > 0.3  # n-gram matching works
