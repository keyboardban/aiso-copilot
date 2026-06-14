"""Bilingual (EN <-> TH) query-expansion bridge for cross-lingual retrieval.

Problem it solves: a Thai webpage audited against English fan-out questions (or
vice versa) gets near-zero lexical scores — BM25/TF-IDF/term-overlap can't match
"definition" against "ความหมาย". There is no paid translation API in this
project, so instead of translating, we keep a small deterministic domain
glossary (the same lexicon-driven approach used in entity_extractor.py) plus
per-intent cue words in both languages.

Used ONLY when the question language differs from the page language
(hybrid_coverage.py decides). Same-language audits never touch this module, so
monolingual behavior is unchanged.
"""

import re

# English domain/keyword -> Thai equivalents. Lowercase keys; matched as whole
# words against the question. Deliberately scoped to the SEO / AI-search /
# digital-marketing domain this tool audits.
EN_TO_TH = {
    "seo": ["เอสอีโอ"],
    "geo": ["จีอีโอ"],
    "ai": ["เอไอ", "ปัญญาประดิษฐ์"],
    "search": ["ค้นหา", "การค้นหา", "เสิร์ช"],
    "optimization": ["เพิ่มประสิทธิภาพ", "ปรับแต่ง", "การปรับให้เหมาะสม"],
    "agency": ["เอเจนซี", "บริษัทรับทำ", "รับทำ"],
    "service": ["บริการ"],
    "services": ["บริการ"],
    "content": ["เนื้อหา", "คอนเทนต์"],
    "marketing": ["การตลาด"],
    "schema": ["สคีมา", "ข้อมูลโครงสร้าง"],
    "markup": ["มาร์กอัป", "ข้อมูลโครงสร้าง"],
    "citation": ["การอ้างอิง", "อ้างอิง"],
    "citations": ["การอ้างอิง", "อ้างอิง"],
    "visibility": ["การมองเห็น", "การปรากฏ", "การถูกพบ"],
    "brand": ["แบรนด์", "ตราสินค้า"],
    "business": ["ธุรกิจ"],
    "businesses": ["ธุรกิจ"],
    "cost": ["ราคา", "ค่าใช้จ่าย"],
    "price": ["ราคา"],
    "pricing": ["ราคา", "ค่าบริการ"],
    "definition": ["คือ", "คืออะไร", "ความหมาย"],
    "meaning": ["ความหมาย", "หมายถึง"],
    "tool": ["เครื่องมือ"],
    "tools": ["เครื่องมือ"],
    "data": ["ข้อมูล"],
    "process": ["ขั้นตอน", "กระบวนการ"],
    "result": ["ผลลัพธ์"],
    "results": ["ผลลัพธ์"],
    "example": ["ตัวอย่าง"],
    "examples": ["ตัวอย่าง"],
    "website": ["เว็บไซต์", "เว็บ"],
    "page": ["หน้าเว็บ", "เพจ"],
    "google": ["กูเกิล"],
    "ranking": ["อันดับ", "การจัดอันดับ"],
    "keyword": ["คีย์เวิร์ด", "คำค้นหา"],
    "keywords": ["คีย์เวิร์ด", "คำค้นหา"],
    "audience": ["กลุ่มเป้าหมาย", "ผู้ชม"],
    "strategy": ["กลยุทธ์"],
    "benefit": ["ประโยชน์"],
    "benefits": ["ประโยชน์"],
    "measure": ["วัดผล", "การวัด"],
    "trust": ["ความน่าเชื่อถือ", "น่าเชื่อถือ"],
}

# Per-intent cue words: what the intent looks like expressed in each language.
# When cross-lingual, a cue group in the PAGE's language is added so that a page
# answering the intent (even with different vocabulary) still registers.
INTENT_CUES_TH = {
    "definition": ["คืออะไร", "ความหมาย", "หมายถึง"],
    "comparison": ["ต่างจาก", "แตกต่าง", "เทียบ", "ดีกว่า"],
    "implementation": ["วิธีทำ", "ทำอย่างไร", "เริ่ม", "ขั้นตอน"],
    "measurement": ["วัดผล", "วัดอย่างไร", "ตัวชี้วัด"],
    "commercial": ["ราคา", "รับทำ", "บริการ", "จ้าง", "ค่าใช้จ่าย"],
    "technical": ["เครื่องมือ", "ข้อมูล", "เทคนิค"],
    "trust": ["น่าเชื่อถือ", "อ้างอิง", "รีวิว", "ผลงาน"],
    "local": ["ไทย", "ในประเทศไทย", "กรุงเทพ"],
    "schema": ["สคีมา", "ข้อมูลโครงสร้าง"],
    "proof": ["ผลงาน", "ตัวอย่างผลงาน", "ผลลัพธ์", "เคส"],
    "content_strategy": ["เนื้อหา", "โครงสร้างเนื้อหา", "คอนเทนต์"],
}
INTENT_CUES_EN = {
    "definition": ["definition", "meaning", "what is"],
    "comparison": ["versus", "difference", "compared", "different from"],
    "implementation": ["how to", "steps", "guide", "getting started"],
    "measurement": ["measure", "metrics", "kpi", "track"],
    "commercial": ["price", "cost", "hire", "service", "agency"],
    "technical": ["tools", "data", "technical", "requirements"],
    "trust": ["trusted", "credible", "reviews", "results", "citation"],
    "local": ["thailand", "local", "near me"],
    "schema": ["schema", "structured data", "markup"],
    "proof": ["case study", "results", "portfolio", "proof"],
    "content_strategy": ["content", "structure", "headings"],
}

# Reverse map (Thai whole-word -> English equivalents), built once.
TH_TO_EN = {}
for _en, _ths in EN_TO_TH.items():
    for _th in _ths:
        TH_TO_EN.setdefault(_th, [])
        if _en not in TH_TO_EN[_th]:
            TH_TO_EN[_th].append(_en)

_THAI_RE = re.compile(r"[฀-๿]")


def _is_thai(term: str) -> bool:
    return bool(_THAI_RE.search(term or ""))


def equivalents(term: str) -> list:
    """Cross-language equivalents of a single content term (either direction)."""
    term = (term or "").lower()
    if _is_thai(term):
        return list(TH_TO_EN.get(term, []))
    return list(EN_TO_TH.get(term, []))


def intent_cues(intent: str, want_thai: bool) -> list:
    """Cue words for an intent in the requested language."""
    table = INTENT_CUES_TH if want_thai else INTENT_CUES_EN
    return list(table.get(intent, []))


def bridge_terms(terms, intent: str, target_is_thai: bool) -> list:
    """Flat list of expansion terms (in the target/page language) for a set of
    question content terms plus the intent's cue words. Deduplicated, order
    preserved. Used to enrich the BM25/TF-IDF retrieval query."""
    out = []
    seen = set()

    def add(value: str) -> None:
        value = value.strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)

    for term in terms:
        for equiv in equivalents(term):
            # only keep equivalents that are in the target language
            if _is_thai(equiv) == target_is_thai:
                add(equiv)
    for cue in intent_cues(intent, want_thai=target_is_thai):
        add(cue)
    return out
