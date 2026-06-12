"""Query fan-out generation: expand a topic into the question set an
AI-assisted search system would likely explore.

Deterministic template generation always runs and always works. An optional
LLM provider (OpenRouter free model / local Ollama) may append extra
questions; any LLM failure silently leaves the deterministic set intact.
"""

from src.config import MAX_FANOUT_QUESTIONS
from src.query.templates import (
    BRAND_TEMPLATES,
    LOCATION_TEMPLATES,
    TEMPLATE_QUESTIONS,
    classify_intent,
)


def _first_or_empty(values) -> str:
    if isinstance(values, list) and values:
        return str(values[0])
    return ""


def generate_fanout(
    topic: str,
    audience: str = "",
    seeds: list = None,
    entities: dict = None,
    llm=None,
    max_questions: int = MAX_FANOUT_QUESTIONS,
) -> dict:
    """Return {"seed_questions", "fanout_questions", "llm_used", "llm_note"}.

    fanout_questions entries are {"question", "intent", "source"} where source
    is seed | template | openrouter | ollama. ("seed" is a documented addition
    to the spec enum so seed questions flow through coverage scoring too.)
    """
    topic = (topic or "").strip() or "AI Search Optimization"
    audience = (audience or "").strip() or "businesses"
    seeds = seeds or []
    entities = entities or {}

    questions = []
    seen = set()

    def add(question: str, intent: str, source: str) -> bool:
        question = " ".join((question or "").split())
        key = question.lower().rstrip("?")
        if not question or key in seen:
            return False
        seen.add(key)
        questions.append({"question": question, "intent": intent, "source": source})
        return True

    # 1) user/sample seed questions, classified by the bilingual rule cascade
    seed_questions = []
    for seed in seeds:
        seed = seed.strip()
        if seed and add(seed, classify_intent(seed), "seed"):
            seed_questions.append(seed)

    # 2) deterministic templates (the no-LLM backbone)
    context = {"topic": topic, "audience": audience}
    for template, intent in TEMPLATE_QUESTIONS:
        add(template.format(**context), intent, "template")

    location = _first_or_empty(entities.get("locations"))
    if location:
        for template, intent in LOCATION_TEMPLATES:
            add(template.format(topic=topic, location=location), intent, "template")
    brand = _first_or_empty(entities.get("brand"))
    if brand:
        for template, intent in BRAND_TEMPLATES:
            add(template.format(topic=topic, brand=brand), intent, "template")

    # 3) optional LLM extras — additive only, never required
    llm_used = False
    llm_note = "Deterministic templates only (no-LLM mode)."
    if llm is not None and getattr(llm, "mode", "no_llm") != "no_llm" and llm.available():
        from src.llm.prompt_builder import build_fanout_prompt, parse_question_lines

        response = llm.complete(build_fanout_prompt(topic, audience, seed_questions))
        if response:
            added = 0
            for question in parse_question_lines(response):
                if len(questions) >= max_questions:
                    break
                if add(question, classify_intent(question), llm.mode):
                    added += 1
            if added:
                llm_used = True
                llm_note = f"Templates + {added} extra question(s) from {llm.mode}."
            else:
                llm_note = f"{llm.mode} returned no usable questions; using templates only."
        else:
            llm_note = f"{llm.mode} unavailable or errored; fell back to templates."

    return {
        "seed_questions": seed_questions,
        "fanout_questions": questions[:max_questions],
        "llm_used": llm_used,
        "llm_note": llm_note,
    }
