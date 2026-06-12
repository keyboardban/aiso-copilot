"""Turn normalized Search Console rows into AI-Search content opportunities.

Pure pandas/rule logic. Each row yields at most ONE opportunity — the highest-
precedence matching rule — so the output reads like a prioritized analyst
sheet rather than the same query repeated under different labels. Secondary
matching signals are appended to the reason.
"""

import re

from src.config import SC_LOW_CTR, SC_MIN_IMPRESSIONS, SC_STRIKING_DISTANCE

_QUESTION_RE = re.compile(
    r"^(?:what|how|why|who|when|where|which|is|are|can|does|do|should)\b|"
    r"คืออะไร|อย่างไร|ทำไม|วิธี|ยังไง|ไหม|อะไร", re.I)
_COMMERCIAL_RE = re.compile(r"pric(?:e|ing)|cost|hire|agency|company|services?|quote|ราคา|จ้าง|บริษัท", re.I)

# precedence order: first match becomes the row's primary opportunity
_RULE_ORDER = [
    "intent_mismatch",
    "high_impression_low_ctr",
    "low_ctr_despite_rank",
    "striking_distance",
    "ai_answer_opportunity",
]

_ACTIONS = {
    "intent_mismatch": (
        "Point this query at a service/commercial page, or add pricing and service "
        "specifics to the landing page."
    ),
    "high_impression_low_ctr": (
        "Rewrite the title/meta to answer the query directly, and open the page with "
        "a quotable direct-answer block."
    ),
    "low_ctr_despite_rank": (
        "Align the title and meta description with the query's exact language and intent."
    ),
    "striking_distance": (
        "Add a dedicated section (or FAQ entry) answering this query verbatim, with "
        "supporting evidence and internal links."
    ),
    "ai_answer_opportunity": (
        "Add a question-styled heading with a 2–3 sentence direct answer, and mark it "
        "up as FAQ content if it fits."
    ),
}


def _priority(impressions: float, boost: bool = False) -> str:
    if impressions >= 1000 or (boost and impressions >= 200):
        return "high"
    if impressions >= 300:
        return "medium"
    return "low"


def _matching_rules(query, page, impressions, ctr, position, is_question) -> dict:
    """Return {rule_name: reason} for every rule this row matches."""
    matches = {}
    if _COMMERCIAL_RE.search(query) and "/blog/" in page.lower() and impressions >= 100:
        matches["intent_mismatch"] = (
            f"Commercial-intent query lands on a blog page (position {position:.0f})."
        )
    if impressions >= SC_MIN_IMPRESSIONS and ctr < SC_LOW_CTR and position <= 20:
        matches["high_impression_low_ctr"] = (
            f"{impressions:.0f} impressions but only {ctr:.2f}% CTR at position "
            f"{position:.1f} — the snippet is not winning the click."
        )
    if position and position <= 5 and impressions >= 200 and ctr < 2.0:
        matches["low_ctr_despite_rank"] = (
            f"Ranks position {position:.1f} but CTR is only {ctr:.2f}% — the title/meta "
            "likely mismatch the query promise."
        )
    low, high = SC_STRIKING_DISTANCE
    if low <= position <= high and impressions >= 100:
        matches["striking_distance"] = (
            f"Average position {position:.1f} — close to the range answer engines pull "
            "sources from."
        )
    if is_question and impressions >= 100:
        matches["ai_answer_opportunity"] = (
            "Question-style query — exactly the form AI assistants fan out into."
        )
    return matches


def find_opportunities(df) -> dict:
    """Return {"opportunities": [...], "summary": {...}} from a normalized
    Search Console DataFrame (see csv_loader)."""
    opportunities = []

    for row in df.itertuples(index=False):
        query = str(row.query)
        page = str(row.page)
        impressions = float(row.impressions or 0)
        ctr = float(row.ctr or 0)
        position = float(row.position or 0)
        is_question = bool(_QUESTION_RE.search(query))

        matches = _matching_rules(query, page, impressions, ctr, position, is_question)
        if not matches:
            continue
        primary = next(rule for rule in _RULE_ORDER if rule in matches)
        secondary = [rule for rule in matches if rule != primary]
        reason = matches[primary]
        if secondary:
            reason += " Also: " + ", ".join(s.replace("_", " ") for s in secondary) + "."

        boost = primary == "intent_mismatch" or (is_question and position <= 15)
        opportunities.append({
            "query": query,
            "page": page,
            "clicks": int(row.clicks or 0),
            "impressions": int(impressions),
            "ctr": ctr,
            "position": position,
            "opportunity_type": primary,
            "secondary_signals": secondary,
            "priority": _priority(impressions, boost=boost),
            "reason": reason,
            "recommended_action": _ACTIONS[primary],
        })

    order = {"high": 0, "medium": 1, "low": 2}
    opportunities.sort(key=lambda o: (order[o["priority"]], -o["impressions"]))
    opportunities = opportunities[:40]

    by_type = {}
    for opp in opportunities:
        by_type[opp["opportunity_type"]] = by_type.get(opp["opportunity_type"], 0) + 1
    summary = {
        "total_opportunities": len(opportunities),
        "by_type": by_type,
        "high_priority": sum(1 for o in opportunities if o["priority"] == "high"),
        "question_queries": int(df["query"].astype(str).str.contains(_QUESTION_RE, regex=True).sum()),
    }
    return {"opportunities": opportunities, "summary": summary}
