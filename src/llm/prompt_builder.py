"""Prompts for the optional LLM enhancement layer.

LLMs are used ONLY for additive polish (extra fan-out questions, nicer answer
simulations, report summary wording) — never for scoring, extraction,
retrieval, or schema validation. Prompts enforce strict grounding in the
provided evidence to avoid hallucinated claims.
"""

import re

from src.utils.text import truncate

FANOUT_SYSTEM = (
    "You generate realistic search questions that users ask AI assistants. "
    "Output plain questions, one per line, no numbering, no commentary."
)

# Few-shot exemplars: worked (topic, audience -> questions) pairs that show the
# desired shape — a mix of buying-stage and learning-stage questions, one per
# line, no numbering. Using a different domain than the audit's keeps the model
# pattern-matching on form rather than copying content.
FANOUT_SHOTS = [
    {
        "topic": "managed cloud hosting",
        "audience": "e-commerce startups",
        "questions": [
            "What is managed cloud hosting and how is it different from regular hosting?",
            "How much does managed cloud hosting cost for a small online store?",
            "Can managed hosting handle traffic spikes during a flash sale?",
            "What should I look for when choosing a managed hosting provider?",
            "How do I migrate my store to managed hosting without downtime?",
            "Is managed hosting worth it versus hiring a DevOps engineer?",
        ],
    },
    {
        "topic": "dental implants",
        "audience": "adults aged 40-60",
        "questions": [
            "What are dental implants and how do they work?",
            "How long do dental implants last compared to dentures?",
            "How much do dental implants cost and does insurance cover them?",
            "Is the dental implant procedure painful?",
            "Who is a good candidate for dental implants?",
            "How do I care for dental implants after surgery?",
        ],
    },
]


def _format_shot(shot: dict) -> str:
    questions = "\n".join(shot["questions"])
    return (
        f"Topic: {shot['topic']}\nAudience: {shot['audience']}\nQuestions:\n{questions}"
    )


def build_fanout_prompt(topic: str, audience: str, seeds: list = None,
                        n_shots: int = 2) -> str:
    """Few-shot fan-out prompt.

    Prepends ``n_shots`` worked examples (see FANOUT_SHOTS) before the real
    task so the model imitates the question style and learning/buying mix.
    Set ``n_shots=0`` for the original zero-shot behavior.
    """
    shots = FANOUT_SHOTS[: max(0, n_shots)]
    example_block = ""
    if shots:
        examples = "\n\n".join(_format_shot(shot) for shot in shots)
        example_block = (
            "Here are examples of good question sets for other topics:\n\n"
            f"{examples}\n\n"
            "Now do the same for this topic:\n\n"
        )

    seed_block = ""
    if seeds:
        listed = "\n".join(f"- {s}" for s in seeds[:10])
        seed_block = f"Already covered (do NOT repeat these):\n{listed}\n\n"

    return (
        f"{example_block}"
        f"Topic: {topic}\nAudience: {audience}\n\n"
        f"{seed_block}"
        "Write 6 questions this audience would realistically ask an AI assistant "
        "about the topic. Mix buying-stage and learning-stage questions, matching "
        "the style of the examples above. One question per line, nothing else."
    )


ANSWER_SYSTEM = (
    "You simulate how an AI search assistant would answer using ONLY the "
    "supplied page evidence. Never invent facts. If the evidence is "
    "insufficient, say so explicitly and name what is missing."
)


def build_answer_prompt(question: str, evidence: list) -> str:
    if evidence:
        evidence_block = "\n\n".join(
            f"[Evidence {i + 1} — section: {e['section']}]\n{e['text']}"
            for i, e in enumerate(evidence[:4])
        )
    else:
        evidence_block = "(no relevant evidence found on the page)"
    return (
        f"Question: {question}\n\nPage evidence:\n{evidence_block}\n\n"
        "Write a 2–4 sentence answer USING ONLY this evidence. "
        "Then on a final line write 'MISSING:' followed by what the page would "
        "need to add for a complete answer (or 'nothing')."
    )


POLISH_SYSTEM = (
    "You are a senior AI Search consultant editing an audit summary. Keep every "
    "fact and number unchanged; do not add claims or guarantees. Improve flow "
    "and tone only."
)


def build_polish_prompt(executive_summary: str) -> str:
    return (
        "Rewrite this audit executive summary in a polished consultant tone "
        "(2 short paragraphs max). Keep all scores and facts exactly as given:\n\n"
        f"{truncate(executive_summary, 1800)}"
    )


def parse_question_lines(text: str) -> list:
    """Parse LLM output into clean question strings."""
    questions = []
    seen = set()
    for line in (text or "").splitlines():
        line = re.sub(r"^\s*(?:[-*•>]|\d+[.)])\s*", "", line).strip().strip('"')
        if not line or len(line) < 8 or len(line) > 300:
            continue
        if not (line.endswith("?") or re.match(r"^(what|how|why|who|when|where|does|is|can|should|ทำ|อะไร|วิธี)", line, re.I)):
            continue
        key = line.lower().rstrip("?")
        if key in seen:
            continue
        seen.add(key)
        questions.append(line)
        if len(questions) >= 10:
            break
    return questions
