"""LLM provider abstraction.

Contract: providers NEVER raise from complete() — they return a string or
None. None means "use the deterministic template path". This keeps the core
pipeline structurally incapable of failing because of an LLM.

Modes: no_llm (default, always works) | openrouter (optional, user-supplied
free model slug) | ollama (optional, local). get_provider() resolves a mode
plus credentials into (provider, human-readable status), falling back to
no_llm whenever prerequisites are missing.
"""

from abc import ABC, abstractmethod

from src.config import (
    MODE_NO_LLM,
    MODE_OLLAMA,
    MODE_OPENROUTER,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    OPENROUTER_MODELS,
)


def provider_label(provider) -> str:
    """Readable source tag for a provider, e.g. 'openrouter:llama-3.3-70b'.

    Used to tag which model produced each fan-out question in multi-agent mode.
    """
    mode = getattr(provider, "mode", "llm")
    model = getattr(provider, "model", "") or ""
    if not model:
        return mode
    short = model.split("/")[-1].replace(":free", "")
    return f"{mode}:{short}"


def build_openrouter_agents(api_key: str = None, models=None) -> list:
    """Build one OpenRouterProvider per model slug for multi-agent fan-out.

    Returns [] when no API key is available (→ deterministic templates). Each
    agent fails independently: a bad/stale slug just yields no questions, it
    never breaks the others or the app.
    """
    from src.llm.openrouter_provider import OpenRouterProvider

    key = (api_key or OPENROUTER_API_KEY or "").strip()
    if not key:
        return []
    slugs = models if models else OPENROUTER_MODELS
    if isinstance(slugs, str):
        from src.config import _parse_model_list

        slugs = _parse_model_list(slugs)
    agents = []
    seen = set()
    for slug in slugs:
        slug = (slug or "").strip()
        if slug and slug not in seen:
            seen.add(slug)
            agents.append(OpenRouterProvider(api_key=key, model=slug))
    return agents


class LLMProvider(ABC):
    mode = "base"
    label = "Base provider"

    @abstractmethod
    def available(self) -> bool:
        """Cheap readiness check (config present / server reachable)."""

    @abstractmethod
    def complete(self, prompt: str, system: str = None,
                 max_tokens: int = 700, temperature: float = 0.4):
        """Return generated text, or None on ANY problem (never raises)."""


def get_provider(mode: str, api_key: str = None, model: str = None,
                 base_url: str = None, ollama_model: str = None) -> tuple:
    """Resolve (provider, status_message) for a requested mode.

    Missing keys/models/servers downgrade to no-LLM mode with an explanatory
    status — they never error.
    """
    from src.llm.no_llm_fallback import NoLLMProvider
    from src.llm.ollama_provider import OllamaProvider
    from src.llm.openrouter_provider import OpenRouterProvider

    mode = (mode or MODE_NO_LLM).lower().strip()

    if mode == MODE_OPENROUTER:
        key = (api_key or OPENROUTER_API_KEY or "").strip()
        slug = (model or OPENROUTER_MODEL or "").strip()
        if not key:
            return NoLLMProvider(), (
                "OpenRouter mode selected but no OPENROUTER_API_KEY found — "
                "using no-LLM deterministic fallback."
            )
        if not slug:
            return NoLLMProvider(), (
                "OpenRouter mode selected but no model slug provided — pick a free "
                "model on openrouter.ai/models. Using no-LLM deterministic fallback."
            )
        return OpenRouterProvider(api_key=key, model=slug), (
            f"Using OpenRouter optional mode (model: {slug}). "
            "Any quota/auth/provider error falls back to deterministic templates."
        )

    if mode == MODE_OLLAMA:
        provider = OllamaProvider(
            base_url=(base_url or OLLAMA_BASE_URL),
            model=(ollama_model or model or OLLAMA_MODEL),
        )
        if provider.available():
            return provider, (
                f"Using local Ollama optional mode (model: {provider.model}) at {provider.base_url}."
            )
        return NoLLMProvider(), (
            f"Ollama not reachable at {provider.base_url} (or no model installed) — "
            "using no-LLM deterministic fallback."
        )

    return NoLLMProvider(), "Using no-LLM free deterministic mode (default)."
