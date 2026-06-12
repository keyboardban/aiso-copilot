"""Score combination: bounded, weighted, explainable."""

from src.audit.scoring import compute_scores
from src.config import READINESS_WEIGHTS


def _fake_inputs(structure=80, entity=70, coverage=60, sourceability=50, schema=40, technical=90):
    return dict(
        structure_result={"structure_score": structure, "recommendations": ["Fix titles"], "weaknesses": []},
        entity_result={"entity_clarity_score": entity, "recommendations": ["Name the brand"]},
        coverage_result={"coverage_score": coverage, "coverage_matrix": [
            {"question": "Q1?", "coverage": "Missing", "score": 0.1},
            {"question": "Q2?", "coverage": "Partial", "score": 0.45},
            {"question": "Q3?", "coverage": "Covered", "score": 0.8},
        ]},
        sourceability_result={"sourceability_score": sourceability, "recommendations": ["Add numbers"]},
        schema_result={"schema_score": schema, "missing_types": ["FAQPage"]},
        technical={"score": technical, "issues": ["No meta description found."]},
    )


def test_weights_sum_to_one():
    assert abs(sum(READINESS_WEIGHTS.values()) - 1.0) < 1e-9


def test_overall_is_weighted_blend():
    result = compute_scores(**_fake_inputs())
    expected = round(sum({
        "structure": 80, "entity_clarity": 70, "query_coverage": 60,
        "sourceability": 50, "schema": 40, "technical_extractability": 90,
    }[k] * w for k, w in READINESS_WEIGHTS.items()))
    assert result["overall_ai_search_readiness"] == expected
    assert all(0 <= v <= 100 for v in result["subscores"].values())


def test_scores_clamped_to_0_100():
    result = compute_scores(**_fake_inputs(structure=150, entity=-20, schema=None))
    assert result["subscores"]["structure"] == 100
    assert result["subscores"]["entity_clarity"] == 0
    assert result["subscores"]["schema"] == 0
    assert 0 <= result["overall_ai_search_readiness"] <= 100


def test_priority_actions_structure():
    result = compute_scores(**_fake_inputs(schema=20, sourceability=30))
    actions = result["priority_actions"]
    assert actions, "low subscores must produce actions"
    assert len(actions) <= 8
    for action in actions:
        assert action["priority"] in ("high", "medium", "low")
        assert action["category"] and action["action"]
    priorities = [action["priority"] for action in actions]
    order = {"high": 0, "medium": 1, "low": 2}
    assert priorities == sorted(priorities, key=order.get), "sorted high→low"


def test_missing_questions_surface_in_actions():
    result = compute_scores(**_fake_inputs(coverage=30))
    coverage_actions = [a for a in result["priority_actions"] if a["category"] == "Query coverage"]
    assert any("Q1?" in a["action"] for a in coverage_actions)
