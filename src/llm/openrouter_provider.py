"""Optional OpenRouter provider (chat-completions over plain HTTP).

Strictly opt-in and never required:
  - the user supplies BOTH the API key and the model slug (the user is
    responsible for choosing a free model — none is hardcoded here),
  - any error (auth, quota, rate limit, payment, provider outage, timeout,
    malformed response) is caught, recorded in .last_error, and surfaces as
    None — the analyzer then continues on deterministic templates.
"""

import requests

from src.config import LLM_TIMEOUT, MODE_OPENROUTER, OPENROUTER_ENDPOINT
from src.llm.provider_base import LLMProvider


class OpenRouterProvider(LLMProvider):
    mode = MODE_OPENROUTER
    label = "OpenRouter free optional mode"

    def __init__(self, api_key: str, model: str):
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.last_error = None

    def available(self) -> bool:
        return bool(self.api_key and self.model)

    def complete(self, prompt: str, system: str = None,
                 max_tokens: int = 700, temperature: float = 0.4):
        if not self.available():
            self.last_error = "Missing API key or model slug."
            return None
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            response = requests.post(
                OPENROUTER_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    # courtesy headers OpenRouter uses for attribution
                    "HTTP-Referer": "https://github.com/aiso-copilot",
                    "X-Title": "AISO Copilot",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
                timeout=LLM_TIMEOUT,
            )
            if response.status_code != 200:
                detail = ""
                try:
                    detail = (response.json().get("error") or {}).get("message", "")
                except Exception:
                    detail = response.text[:120]
                self.last_error = f"HTTP {response.status_code}: {detail}".strip()
                return None
            data = response.json()
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
            if not content or not str(content).strip():
                self.last_error = "Empty completion returned."
                return None
            self.last_error = None
            return str(content).strip()
        except requests.exceptions.Timeout:
            self.last_error = f"Timed out after {LLM_TIMEOUT}s."
        except requests.exceptions.RequestException as exc:
            self.last_error = f"Request failed: {exc.__class__.__name__}."
        except Exception as exc:  # malformed JSON, unexpected shape, anything
            self.last_error = f"Unexpected error: {exc.__class__.__name__}."
        return None
