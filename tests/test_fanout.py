"""Fan-out generation must fully work without any LLM."""

from src.query.fanout_generator import generate_fanout
from src.query.templates import INTENTS, classify_intent


def test_template_fanout_without_llm():
    result = generate_fanout("AI Search Optimization", "Thai businesses")
    questions = result["fanout_questions"]
    assert len(questions) >= 20
    assert result["llm_used"] is False
    for item in questions:
        assert item["question"].strip()
        assert item["intent"] in INTENTS
        assert item["source"] in ("seed", "template", "openrouter", "ollama")
        assert "{topic}" not in item["question"] and "{audience}" not in item["question"]


def test_seeds_are_included_and_classified():
    seeds = ["GEO คืออะไร", "AI Search ต่างจาก SEO อย่างไร", "How do you measure AI visibility?"]
    result = generate_fanout("AI Search Optimization", "businesses", seeds=seeds)
    assert result["seed_questions"] == seeds
    seed_rows = [q for q in result["fanout_questions"] if q["source"] == "seed"]
    assert len(seed_rows) == len(seeds)
    by_question = {row["question"]: row["intent"] for row in seed_rows}
    assert by_question["GEO คืออะไร"] == "definition"
    assert by_question["AI Search ต่างจาก SEO อย่างไร"] == "comparison"
    assert by_question["How do you measure AI visibility?"] == "measurement"


def test_no_duplicate_questions():
    seeds = ["What is AI Search Optimization?", "what is ai search optimization"]
    result = generate_fanout("AI Search Optimization", "businesses", seeds=seeds)
    normalized = [q["question"].lower().rstrip("?") for q in result["fanout_questions"]]
    assert len(normalized) == len(set(normalized))


def test_entity_templates_used_when_entities_present():
    entities = {"locations": ["Thailand"], "brand": ["Sample Digital Agency"]}
    result = generate_fanout("AI Search Optimization", "businesses", entities=entities)
    questions = " | ".join(q["question"] for q in result["fanout_questions"])
    assert "Thailand" in questions
    assert "Sample Digital Agency" in questions
    assert any(q["intent"] == "local" for q in result["fanout_questions"])


def test_intent_classifier_bilingual_rules():
    assert classify_intent("Schema markup ช่วย AI Search อย่างไร") == "schema"
    assert classify_intent("ทำอย่างไรให้เว็บไซต์ถูก AI Search อ้างอิง") == "trust"
    assert classify_intent("ธุรกิจไทยควรเริ่มทำ AI Search อย่างไร") == "implementation"
    assert classify_intent("AI Search visibility วัดผลอย่างไร") == "measurement"
    assert classify_intent("Why is my brand invisible to ChatGPT?") in INTENTS
