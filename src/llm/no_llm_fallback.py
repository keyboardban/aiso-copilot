"""The default 'provider': no LLM at all.

complete() always returns None, which every call site interprets as "use the
deterministic template path". This makes no-LLM mode a first-class citizen
rather than an error state.
"""

from src.config import MODE_NO_LLM
from src.llm.provider_base import LLMProvider


class NoLLMProvider(LLMProvider):
    mode = MODE_NO_LLM
    label = "No-LLM free deterministic mode"

    def available(self) -> bool:
        return True  # always usable — it is the fallback

    def complete(self, prompt: str, system: str = None,
                 max_tokens: int = 700, temperature: float = 0.4):
        return None  # signals: use rule-based templates
