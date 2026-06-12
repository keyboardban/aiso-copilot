"""Optional local Ollama provider.

Used only when LLM_MODE=ollama AND a local Ollama server responds. If no
model is configured, the first locally installed model is used. All errors
surface as None (deterministic fallback), never as exceptions.
"""

import requests

from src.config import LLM_TIMEOUT, MODE_OLLAMA
from src.llm.provider_base import LLMProvider


class OllamaProvider(LLMProvider):
    mode = MODE_OLLAMA
    label = "Local Ollama optional mode"

    def __init__(self, base_url: str, model: str = ""):
        self.base_url = (base_url or "http://localhost:11434").rstrip("/")
        self.model = (model or "").strip()
        self.last_error = None
        self._reachable = None

    def available(self) -> bool:
        if self._reachable is not None:
            return self._reachable
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            data = response.json() if response.status_code == 200 else {}
            models = [m.get("name", "") for m in data.get("models", [])]
            if not self.model and models:
                self.model = models[0]  # auto-pick the first installed model
            self._reachable = bool(models) and bool(self.model)
            if not self._reachable:
                self.last_error = "Ollama reachable but no models installed." if not models else None
        except Exception:
            self._reachable = False
            self.last_error = "Ollama server not reachable."
        return self._reachable

    def complete(self, prompt: str, system: str = None,
                 max_tokens: int = 700, temperature: float = 0.4):
        if not self.available():
            return None
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                },
                timeout=LLM_TIMEOUT,
            )
            if response.status_code != 200:
                self.last_error = f"HTTP {response.status_code}: {response.text[:120]}"
                return None
            content = (response.json().get("message") or {}).get("content", "")
            if not content.strip():
                self.last_error = "Empty completion returned."
                return None
            self.last_error = None
            return content.strip()
        except requests.exceptions.RequestException as exc:
            self.last_error = f"Request failed: {exc.__class__.__name__}."
        except Exception as exc:
            self.last_error = f"Unexpected error: {exc.__class__.__name__}."
        return None
