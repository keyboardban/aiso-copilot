"""Combine sub-scores into the overall AI Search Readiness score and derive
priority actions. Weights live in config.READINESS_WEIGHTS; the full formula
is documented in SCORING_RUBRIC.md.
"""

from src.config import READINESS_WEIGHTS


def _clamp(score) -> int:
    try:
        return max(0, min(100, round(float(score))))
    except (TypeError, ValueError):
        return 0


def compute_scores(
    structure_result: dict,
    entity_result: dict,
    coverage_result: dict,
    sourceability_result: dict,
    schema_result: dict,
    technical: dict,
) -> dict:
    """Return {"overall_ai_search_readiness", "subscores", "weights",
    "priority_actions"}."""
    subscores = {
        "structure": _clamp(structure_result.get("structure_score")),
        "entity_clarity": _clamp(entity_result.get("entity_clarity_score")),
        "query_coverage": _clamp(coverage_result.get("coverage_score")),
        "sourceability": _clamp(sourceability_result.get("sourceability_score")),
        "schema": _clamp(schema_result.get("schema_score")),
        "technical_extractability": _clamp((technical or {}).get("score")),
    }
    overall = _clamp(sum(subscores[key] * weight for key, weight in READINESS_WEIGHTS.items()))

    priority_actions = build_priority_actions(
        subscores, structure_result, entity_result, coverage_result,
        sourceability_result, schema_result, technical,
    )
    return {
        "overall_ai_search_readiness": overall,
        "subscores": subscores,
        "weights": dict(READINESS_WEIGHTS),
        "priority_actions": priority_actions,
    }


def _priority_for(score: int) -> str:
    if score < 50:
        return "high"
    if score < 70:
        return "medium"
    return "low"


def build_priority_actions(
    subscores: dict,
    structure_result: dict,
    entity_result: dict,
    coverage_result: dict,
    sourceability_result: dict,
    schema_result: dict,
    technical: dict,
) -> list:
    """Actionable next steps, ordered by impact (weakest weighted areas first)."""
    actions = []

    def add(category: str, action: str, score: int) -> None:
        if action and all(a["action"] != action for a in actions):
            actions.append({"category": category, "action": action,
                            "priority": _priority_for(score)})

    # rank categories by how much weighted headroom an improvement would buy
    deficits = {
        key: (100 - subscores[key]) * READINESS_WEIGHTS[key]
        for key in READINESS_WEIGHTS
    }
    matrix = coverage_result.get("coverage_matrix", [])
    missing = [row for row in matrix if row["coverage"] == "Missing"]
    partial = [row for row in matrix if row["coverage"] == "Partial"]

    for key in sorted(deficits, key=deficits.get, reverse=True):
        score = subscores[key]
        if score >= 90:
            continue
        if key == "query_coverage":
            if missing:
                examples = "; ".join(f"“{row['question']}”" for row in missing[:3])
                add("Query coverage",
                    f"Create content answering the {len(missing)} unanswered fan-out question(s) — start with: {examples}.",
                    score)
            if partial:
                add("Query coverage",
                    f"Strengthen the {len(partial)} partially-answered question(s) with direct, self-contained passages.",
                    score)
        elif key == "structure":
            for rec in structure_result.get("recommendations", [])[:2]:
                add("Structure", rec, score)
        elif key == "sourceability":
            for rec in sourceability_result.get("recommendations", [])[:2]:
                add("Sourceability", rec, score)
        elif key == "schema":
            missing_types = schema_result.get("missing_types", [])
            if missing_types:
                add("Schema",
                    f"Add JSON-LD for: {', '.join(missing_types)} (preview generated in the Schema tab).",
                    score)
        elif key == "entity_clarity":
            for rec in entity_result.get("recommendations", [])[:1]:
                add("Entity clarity", rec, score)
        elif key == "technical_extractability":
            for issue in (technical or {}).get("issues", [])[:1]:
                add("Technical", f"Fix: {issue}", score)

    order = {"high": 0, "medium": 1, "low": 2}
    actions.sort(key=lambda a: order[a["priority"]])
    return actions[:8]
