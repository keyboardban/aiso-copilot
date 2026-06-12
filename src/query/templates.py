"""Deterministic question templates and intent classification for query fan-out.

This is the no-LLM backbone of fan-out generation: 20 core templates (plus a
few entity-aware extras) and a bilingual EN/TH rule cascade for intent
classification. An optional LLM can ADD questions but never replaces this.
"""

import re

INTENTS = [
    "definition",
    "comparison",
    "implementation",
    "measurement",
    "commercial",
    "technical",
    "trust",
    "local",
    "schema",
    "proof",
    "content_strategy",
]

# The 20 core fan-out templates.
TEMPLATE_QUESTIONS = [
    ("What is {topic}?", "definition"),
    ("How does {topic} work?", "definition"),
    ("How is {topic} different from SEO?", "comparison"),
    ("How is {topic} different from traditional search optimization?", "comparison"),
    ("Why is {topic} important for {audience}?", "commercial"),
    ("Who needs {topic}?", "commercial"),
    ("What problems does {topic} solve?", "definition"),
    ("How can a business start with {topic}?", "implementation"),
    ("How do you measure {topic}?", "measurement"),
    ("What are the best practices for {topic}?", "implementation"),
    ("What are common mistakes in {topic}?", "implementation"),
    ("What tools are used for {topic}?", "technical"),
    ("What data is needed for {topic}?", "technical"),
    ("How much effort does {topic} require?", "commercial"),
    ("What should a business look for in a {topic} agency?", "trust"),
    ("How does {topic} help brand visibility?", "content_strategy"),
    ("How does {topic} help AI citations?", "trust"),
    ("What content structure helps {topic}?", "content_strategy"),
    ("Does schema markup help {topic}?", "schema"),
    ("What proof points should a page include for {topic}?", "proof"),
]

# Entity-aware extras, used only when the placeholder entity was detected.
LOCATION_TEMPLATES = [
    ("Why does {topic} matter for businesses in {location}?", "local"),
    ("How should businesses in {location} approach {topic}?", "local"),
]
BRAND_TEMPLATES = [
    ("What does {brand} offer for {topic}?", "commercial"),
]

# Bilingual intent rules, evaluated in order; first match wins.
_INTENT_RULES = [
    ("definition", r"คืออะไร|หมายถึง|^what (is|are)\b|\bdefinition\b|\bmean(s|ing)?\b"),
    ("comparison", r"ต่างจาก|แตกต่าง|เทียบ|ดีกว่า|\bvs\b|\bversus\b|different from|difference|compared?\b"),
    ("measurement", r"วัดผล|วัดอย่างไร|\bmeasure|\bkpi\b|\bmetrics?\b|\btrack(ing)?\b|\broi\b"),
    ("schema", r"\bschema\b|\bmarkup\b|structured data|json-?ld|\bfaqpage\b"),
    ("trust", r"อ้างอิง|น่าเชื่อถือ|เชื่อถือ|\bcite(d)?\b|\bcitation|\bmention(s|ed)?\b|\btrust|\bcredib|\bagency\b|\breliab"),
    ("proof", r"ตัวอย่างผลงาน|ผลลัพธ์|\bcase stud|\bproof\b|\btestimonial|\bresults\b|\bexamples? of\b"),
    ("implementation", r"เริ่ม|วิธีทำ|ทำอย่างไร|\bhow (can|do(es)?|to|should)\b|\bstart\b|\bimplement|\bbest practices\b|\bmistakes\b|\bsteps?\b"),
    ("commercial", r"ราคา|ค่าใช้จ่าย|จ้าง|คุ้ม|\bcost|\bpric|\bhire|\bworth\b|\beffort\b|\bbudget|who needs\b|\bimportant for\b"),
    ("technical", r"เครื่องมือ|ข้อมูลอะไร|\btools?\b|\bsoftware\b|\bplatforms?\b|\bdata\b|\bcrawl|\btechnical\b|\bapi\b"),
    ("local", r"ไทย|กรุงเทพ|\bthailand\b|\bbangkok\b|\blocal\b|\bmarket\b|\bnear me\b"),
    ("content_strategy", r"โครงสร้าง|เนื้อหา|\bcontent\b|\bstructure\b|\bheadings?\b|\bfaq\b|\bwrite\b|\bvisibilit"),
]
_COMPILED_RULES = [(intent, re.compile(pattern, re.I)) for intent, pattern in _INTENT_RULES]


def classify_intent(question: str) -> str:
    text = (question or "").strip()
    for intent, pattern in _COMPILED_RULES:
        if pattern.search(text):
            return intent
    if re.match(r"^\s*(how|ทำ|วิธี)", text, re.I):
        return "implementation"
    return "definition"
