"""Multi-agent OpenRouter fan-out: several free models generate questions that
are merged, deduped, per-model-capped, and source-tagged. No network used."""

import src.llm.provider_base as provider_base
from src.config import MAX_QUESTIONS_PER_AGENT
from src.llm.provider_base import build_openrouter_agents, provider_label
from src.query.fanout_generator import generate_fanout


class FakeAgent:
    """Stand-in OpenRouter provider with canned output (no HTTP)."""

    def __init__(self, model, questions, ok=True):
        self.mode = "openrouter"
        self.model = model
        self._questions = questions
        self._ok = ok

    def available(self):
        return True

    def complete(self, prompt, system=None, max_tokens=700, temperature=0.4):
        if not self._ok:
            return None
        return "\n".join(self._questions)


def test_provider_label_shortens_slug():
    agent = FakeAgent("meta-llama/llama-3.3-70b-instruct:free", [])
    assert provider_label(agent) == "openrouter:llama-3.3-70b-instruct"


def test_multi_agent_merges_and_tags_sources():
    a = FakeAgent("meta-llama/llama-3.3-70b-instruct:free",
                  ["What is AEO and how does it work?",
                   "How much does an AEO audit cost?"])
    b = FakeAgent("qwen/qwen3-next-80b-a3b-instruct:free",
                  ["How do I measure AEO success?",
                   "What is AEO and how does it work?"])  # 2nd is a dup of agent a
    result = generate_fanout("AEO", "businesses", agents=[a, b])

    assert result["llm_used"] is True
    assert result["agents_used"] == [
        "openrouter:llama-3.3-70b-instruct", "openrouter:qwen3-next-80b-a3b-instruct"
    ]
    sources = {q["source"] for q in result["fanout_questions"]}
    assert "openrouter:llama-3.3-70b-instruct" in sources
    assert "openrouter:qwen3-next-80b-a3b-instruct" in sources

    # the duplicate question is not added twice
    texts = [q["question"].lower().rstrip("?") for q in result["fanout_questions"]]
    assert len(texts) == len(set(texts))
    # the cross-agent dup keeps the FIRST agent's source (and appears once)
    dup = [q for q in result["fanout_questions"]
           if q["question"] == "What is AEO and how does it work?"]
    assert len(dup) == 1 and dup[0]["source"] == "openrouter:llama-3.3-70b-instruct"


def test_per_agent_cap_enforced():
    many = [f"Question number {i} about AEO strategy?" for i in range(20)]
    agent = FakeAgent("x/model:free", many)
    result = generate_fanout("AEO", "businesses", agents=[agent])
    from_agent = [q for q in result["fanout_questions"] if q["source"].startswith("openrouter")]
    assert len(from_agent) <= MAX_QUESTIONS_PER_AGENT


def test_one_agent_failing_does_not_break_others():
    good = FakeAgent("good/model:free", ["What is AEO exactly and why now?"])
    bad = FakeAgent("bad/model:free", [], ok=False)
    result = generate_fanout("AEO", "businesses", agents=[bad, good])
    assert result["llm_used"] is True
    assert any(q["source"] == "openrouter:model" for q in result["fanout_questions"])  # good/model
    assert "skipped" in result["llm_note"]


def test_build_agents_requires_key(monkeypatch):
    monkeypatch.setattr(provider_base, "OPENROUTER_API_KEY", "")
    assert build_openrouter_agents(api_key="", models=["a/b:free"]) == []
    agents = build_openrouter_agents(api_key="sk-test", models=["a/b:free", "c/d:free"])
    assert len(agents) == 2 and all(a.mode == "openrouter" for a in agents)


def test_build_agents_dedupes_and_parses_string(monkeypatch):
    agents = build_openrouter_agents(api_key="sk-test",
                                     models="a/b:free, a/b:free\nc/d:free")
    assert [a.model for a in agents] == ["a/b:free", "c/d:free"]
