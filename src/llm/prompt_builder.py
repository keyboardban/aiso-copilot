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


def build_fanout_prompt(topic: str, audience: str, seeds: list = None) -> str:
    seed_block = ""
    if seeds:
        listed = "\n".join(f"- {s}" for s in seeds[:10])
        seed_block = f"\nAlready covered (do NOT repeat these):\n{listed}\n"
    return (
        f"Topic: {topic}\nAudience: {audience}\n{seed_block}\n"
        "Write 6 additional questions this audience would realistically ask an "
        "AI assistant about the topic. Mix buying-stage and learning-stage "
        "questions. One question per line, nothing else."
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
