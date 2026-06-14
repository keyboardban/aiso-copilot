"""Query fan-out generation: expand a topic into the question set an
AI-assisted search system would likely explore.

Deterministic template generation always runs and always works. An optional
LLM provider (OpenRouter free model / local Ollama) may append extra
questions; any LLM failure silently leaves the deterministic set intact.
"""

from src.config import MAX_FANOUT_QUESTIONS
from src.query.templates import (
    BRAND_TEMPLATES,
    COMPARISON_TEMPLATE,
    LOCATION_TEMPLATES,
    TEMPLATE_QUESTIONS,
    classify_intent,
    comparison_alts,
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
    agents: list = None,
    max_questions: int = MAX_FANOUT_QUESTIONS,
) -> dict:
    """Return {"seed_questions", "fanout_questions", "llm_used", "llm_note", "agents_used"}.

    fanout_questions entries are {"question", "intent", "source"} where source
    is seed | template | openrouter:<model> | ollama:<model>. ("seed" is a
    documented addition to the spec enum so seed questions flow through coverage
    scoring too.)

    Multi-agent: when ``agents`` (a list of providers) is given, each provider
    generates questions independently and the results are merged & deduplicated
    for diversity. ``llm`` (single provider) is the back-compatible fallback.
    Either way, any provider failure silently leaves the deterministic set intact.
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

    # comparison questions use baselines guaranteed distinct from the topic
    for alt in comparison_alts(topic, limit=2):
        add(COMPARISON_TEMPLATE.format(topic=topic, alt=alt), "comparison", "template")

    location = _first_or_empty(entities.get("locations"))
    if location:
        for template, intent in LOCATION_TEMPLATES:
            add(template.format(topic=topic, location=location), intent, "template")
    brand = _first_or_empty(entities.get("brand"))
    if brand:
        for template, intent in BRAND_TEMPLATES:
            add(template.format(topic=topic, brand=brand), intent, "template")

    # 3) optional LLM extras — additive only, never required.
    #    Multi-agent: each provider is an independent "agent" generating
    #    questions; results merge & dedupe for diversity.
    from src.config import MAX_QUESTIONS_PER_AGENT
    from src.llm.provider_base import provider_label

    providers = [p for p in (agents or []) if p is not None]
    if not providers and llm is not None:
        providers = [llm]
    providers = [p for p in providers
                 if getattr(p, "mode", "no_llm") != "no_llm" and p.available()]

    llm_used = False
    llm_note = "Deterministic templates only (no-LLM mode)."
    if providers:
        from src.llm.prompt_builder import build_fanout_prompt, parse_question_lines

        prompt = build_fanout_prompt(topic, audience, seed_questions)
        contributions = []  # (label, count)
        failures = []
        for provider in providers:
            label = provider_label(provider)
            if len(questions) >= max_questions:
                break
            response = provider.complete(prompt)
            if not response:
                failures.append(label)
                continue
            added = 0
            for question in parse_question_lines(response):
                if added >= MAX_QUESTIONS_PER_AGENT or len(questions) >= max_questions:
                    break
                if add(question, classify_intent(question), label):
                    added += 1
            if added:
                contributions.append((label, added))

        if contributions:
            llm_used = True
            parts = ", ".join(f"{count} from {label}" for label, count in contributions)
            llm_note = f"Templates + {parts}."
            if failures:
                llm_note += f" (skipped: {', '.join(failures)})"
        elif failures:
            llm_note = f"All agents unavailable/errored ({', '.join(failures)}); fell back to templates."

    return {
        "seed_questions": seed_questions,
        "fanout_questions": questions[:max_questions],
        "llm_used": llm_used,
        "llm_note": llm_note,
        "agents_used": [provider_label(p) for p in providers],
    }
