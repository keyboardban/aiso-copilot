"""Error-analysis fixes: comparison dedup, mashed-token handling, and
cross-lingual (EN question vs TH page) retrieval bridging."""

from src.crawler.extract_content import extract_content
from src.query.fanout_generator import generate_fanout
from src.query.templates import comparison_alts
from src.retrieval.chunker import build_chunks
from src.retrieval.hybrid_coverage import _term_present, evaluate_coverage

THAI_PAGE = """<html><body><main>
<h1>รับทำ SEO และ AI Search Optimization สำหรับธุรกิจไทย</h1>
<h2>SEO คืออะไร</h2>
<p>SEO หรือ การปรับแต่งเว็บไซต์ คือ กระบวนการเพิ่มประสิทธิภาพเนื้อหาเพื่อให้เว็บไซต์ถูกค้นหาเจอ
และช่วยเพิ่มการมองเห็นแบรนด์บนกูเกิล</p>
<h2>บริการของเรา</h2>
<p>เราเป็นเอเจนซีรับทำ SEO และการตลาดออนไลน์ มีบริการวางกลยุทธ์เนื้อหาและการวัดผลอันดับ
ด้วยเครื่องมือและข้อมูลที่แม่นยำ</p>
<h2>ราคาและค่าบริการ</h2>
<p>ค่าบริการขึ้นอยู่กับขอบเขตงาน เรามีตัวอย่างผลงานและผลลัพธ์จริง</p>
</main></body></html>"""


# --- Check 2: comparison dedup ------------------------------------------------

def test_comparison_never_duplicates_topic():
    for topic in ["SEO", "seo", "AI Search Optimization", "traditional search optimization"]:
        result = generate_fanout(topic, "businesses")
        for q in result["fanout_questions"]:
            if q["intent"] == "comparison":
                # the phrase "different from X" must not have X == topic
                tail = q["question"].lower().split("different from")[-1].strip(" ?")
                assert tail != topic.lower(), f"duplicate entity in: {q['question']}"


def test_comparison_alts_distinct_from_topic():
    alts = comparison_alts("SEO", limit=2)
    assert "SEO" not in alts and len(alts) == 2
    assert comparison_alts("", limit=2)  # empty topic still yields baselines


# --- Check 3: mashed / concatenated tokens ------------------------------------

def test_html_extraction_spaces_inline_elements():
    html = ("<main><h2><span>DATA-LED</span><span>CREATIVE-POWERED</span>"
            "<span>OUTCOME-DRIVEN</span></h2></main>")
    page = extract_content(html, "html")
    assert page["headings"]["h2"] == ["DATA-LED CREATIVE-POWERED OUTCOME-DRIVEN"]


def test_term_present_substring_fallback():
    # mashed token still matches a meaningful term / whitelisted acronym
    assert _term_present("seo", {"seoservices"}) is True
    assert _term_present("content", {"contentstrategy"}) is True
    # but not a spurious short substring inside an unrelated word
    assert _term_present("ai", {"maintain"}) is False


# --- Check 1: cross-lingual bridge --------------------------------------------

def _coverage_for_english_questions_on_thai_page():
    page = extract_content(THAI_PAGE, "html")
    chunks = build_chunks(page)
    questions = generate_fanout("SEO", "Thai businesses")["fanout_questions"]
    return evaluate_coverage(chunks, questions)


def test_crosslingual_bridge_lifts_coverage():
    result = _coverage_for_english_questions_on_thai_page()
    # the bridge must register in the method and produce real coverage
    assert "cross-lingual bridge" in result["method"]
    assert result["coverage_score"] > 15, "bilingual bridge should lift cross-lingual coverage"
    statuses = {r["coverage"] for r in result["coverage_matrix"]}
    assert "Covered" in statuses or "Partial" in statuses


def test_monolingual_thai_not_flagged_crosslingual():
    # Thai questions on a Thai page must NOT trigger the cross-lingual path
    page = extract_content(THAI_PAGE, "html")
    chunks = build_chunks(page)
    questions = [{"question": "SEO คืออะไร", "intent": "definition", "source": "seed"}]
    result = evaluate_coverage(chunks, questions)
    assert "cross-lingual bridge" not in result["method"]
