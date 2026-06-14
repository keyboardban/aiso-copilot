"""Small hand-labeled cross-lingual coverage dataset.

Purpose: give the weight-tuning question ("should the blend change for bilingual
mismatch?") a data-grounded answer instead of a guess. Each case is a page in
one language plus questions in the OTHER language, with an author-judged expected
coverage label.

Labels are deliberate human judgments about whether the page's VISIBLE content
answers the question — Covered (directly answered), Partial (related/implied but
incomplete), Missing (not addressed). They encode intent, not tokens, so they
are a fair target for any scoring blend. Small (n≈20) and subjective by nature;
treat results as directional, not definitive.
"""

# --- Case 1: Thai SEO agency page, audited with ENGLISH questions -------------
THAI_PAGE = """<html><body><main>
<h1>รับทำ SEO และ AI Search Optimization สำหรับธุรกิจไทย</h1>

<h2>SEO คืออะไร</h2>
<p>SEO หรือ การปรับแต่งเว็บไซต์ คือ กระบวนการเพิ่มประสิทธิภาพเนื้อหาของเว็บไซต์
เพื่อให้ถูกค้นหาเจอได้ง่ายขึ้นบนกูเกิล และช่วยเพิ่มการมองเห็นแบรนด์ของคุณ
ต่อกลุ่มเป้าหมายที่กำลังค้นหาสินค้าและบริการ</p>

<h2>บริการของเรา</h2>
<p>เราเป็นเอเจนซีรับทำ SEO และการตลาดออนไลน์ครบวงจร ให้บริการวางกลยุทธ์เนื้อหา
ทำคอนเทนต์ ปรับโครงสร้างเว็บไซต์ และการวัดผลอันดับอย่างต่อเนื่อง
ด้วยเครื่องมือและข้อมูลที่แม่นยำ เหมาะสำหรับธุรกิจ SME และแบรนด์ที่ต้องการเติบโต</p>

<h2>ราคาและค่าบริการ</h2>
<p>ค่าบริการเริ่มต้นขึ้นอยู่กับขอบเขตงานและการแข่งขันของแต่ละอุตสาหกรรม
เรามีตัวอย่างผลงานและผลลัพธ์จริงจากลูกค้าให้พิจารณาก่อนตัดสินใจ</p>

<h2>วิธีเริ่มต้นทำ SEO กับเรา</h2>
<p>ขั้นตอนการทำงานของเราเริ่มจากการตรวจสอบเว็บไซต์ วิเคราะห์คู่แข่ง วางกลยุทธ์
จากนั้นลงมือปรับแต่งเนื้อหาและโครงสร้างอย่างเป็นระบบ พร้อมรายงานผลทุกเดือน</p>
</main></body></html>"""

# Each: (question, intent, expected_coverage) — expected vs the THAI page above.
THAI_PAGE_QUESTIONS = [
    # Directly answered → Covered
    ("What is SEO?", "definition", "Covered"),
    ("What services does this agency offer?", "commercial", "Covered"),
    ("Who is SEO for / who needs it?", "commercial", "Covered"),
    ("How does SEO help brand visibility?", "content_strategy", "Covered"),
    ("How can a business get started with SEO here?", "implementation", "Covered"),
    ("What is the process or steps for SEO?", "implementation", "Covered"),
    # Mentioned but not fully answered → Partial
    ("How much does SEO cost?", "commercial", "Partial"),
    ("How do you measure SEO results?", "measurement", "Partial"),
    ("What tools are used for SEO?", "technical", "Partial"),
    ("What proof points or case studies do you have?", "proof", "Partial"),
    # Not addressed on the page → Missing
    ("How is SEO different from traditional search optimization?", "comparison", "Missing"),
    ("What are common mistakes in SEO?", "implementation", "Missing"),
    ("Does schema markup help SEO?", "schema", "Missing"),
    ("How does SEO help AI citations?", "trust", "Missing"),
    ("What is the contract length or cancellation policy?", "commercial", "Missing"),
]

# --- Case 2: English SEO page, audited with THAI questions (reverse direction) -
ENGLISH_PAGE = """<html><body><main>
<h1>AI Search Optimization Services for Growing Brands</h1>

<h2>What is AI Search Optimization?</h2>
<p>AI Search Optimization is the practice of structuring your website content so
AI assistants can understand, retrieve, and cite it when they answer questions.
It improves your brand's visibility inside generated answers.</p>

<h2>Our Services</h2>
<p>We are a digital marketing agency offering content strategy, structured data
implementation, and ongoing measurement of your AI search visibility using
analytics tools and Search Console data.</p>

<h2>How We Work</h2>
<p>Our process starts with an audit of your site, followed by a content and
schema strategy, then systematic implementation with monthly reporting.</p>
</main></body></html>"""

ENGLISH_PAGE_QUESTIONS = [
    ("AI Search Optimization คืออะไร", "definition", "Covered"),
    ("บริการมีอะไรบ้าง", "commercial", "Covered"),
    ("ขั้นตอนการทำงานเป็นอย่างไร", "implementation", "Covered"),
    ("วัดผลอย่างไร", "measurement", "Partial"),
    ("ราคาเท่าไหร่", "commercial", "Missing"),
    ("มีผลงานตัวอย่างไหม", "proof", "Missing"),
]


def all_cases():
    """Return [(label, page_html, [(question, intent, expected), ...]), ...]."""
    return [
        ("TH page / EN questions", THAI_PAGE, THAI_PAGE_QUESTIONS),
        ("EN page / TH questions", ENGLISH_PAGE, ENGLISH_PAGE_QUESTIONS),
    ]


def label_counts():
    counts = {"Covered": 0, "Partial": 0, "Missing": 0}
    for _, _, questions in all_cases():
        for _, _, expected in questions:
            counts[expected] += 1
    return counts
