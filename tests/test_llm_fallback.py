"""The app must never fail because an LLM is unavailable."""

import requests

import src.llm.provider_base as provider_base
from src.llm.no_llm_fallback import NoLLMProvider
from src.llm.openrouter_provider import OpenRouterProvider
from src.llm.provider_base import get_provider
from src.query.fanout_generator import generate_fanout


def _isolate_env(monkeypatch):
    monkeypatch.setattr(provider_base, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(provider_base, "OPENROUTER_MODEL", "")


def test_missing_key_falls_back_to_no_llm(monkeypatch):
    _isolate_env(monkeypatch)
    provider, status = get_provider("openrouter")
    assert isinstance(provider, NoLLMProvider)
    assert "fallback" in status.lower()


def test_missing_model_slug_falls_back(monkeypatch):
    _isolate_env(monkeypatch)
    provider, status = get_provider("openrouter", api_key="sk-test")
    assert isinstance(provider, NoLLMProvider)
    assert "model" in status.lower()


def test_no_llm_provider_returns_none():
    provider = NoLLMProvider()
    assert provider.available() is True
    assert provider.complete("anything") is None


def test_openrouter_network_error_returns_none(monkeypatch):
    def boom(*args, **kwargs):
        raise requests.exceptions.ConnectionError("offline")

    monkeypatch.setattr("src.llm.openrouter_provider.requests.post", boom)
    provider = OpenRouterProvider(api_key="sk-test", model="some/free-model")
    assert provider.complete("hello") is None
    assert provider.last_error


def test_openrouter_quota_error_returns_none(monkeypatch):
    class FakeResponse:
        status_code = 429

        @staticmethod
        def json():
            return {"error": {"message": "Rate limit exceeded"}}

        text = "rate limited"

    monkeypatch.setattr("src.llm.openrouter_provider.requests.post",
                        lambda *a, **k: FakeResponse())
    provider = OpenRouterProvider(api_key="sk-test", model="some/free-model")
    assert provider.complete("hello") is None
    assert "429" in provider.last_error


def test_fanout_still_works_when_llm_errors(monkeypatch):
    monkeypatch.setattr("src.llm.openrouter_provider.requests.post",
                        lambda *a, **k: (_ for _ in ()).throw(requests.exceptions.Timeout()))
    provider = OpenRouterProvider(api_key="sk-test", model="some/free-model")
    result = generate_fanout("AI Search Optimization", "businesses", llm=provider)
    assert len(result["fanout_questions"]) >= 20  # deterministic templates intact
    assert result["llm_used"] is False
    assert "fell back" in result["llm_note"]


def test_unknown_mode_defaults_to_no_llm():
    provider, status = get_provider("definitely-not-a-mode")
    assert isinstance(provider, NoLLMProvider)
    assert "no-llm" in status.lower()
