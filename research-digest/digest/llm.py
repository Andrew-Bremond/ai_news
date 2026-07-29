"""Pluggable LLM providers.

One interface, three adapters, no vendor SDKs — just `requests`. Adding a
fourth provider means adding a class and one registry line; nothing else in
the pipeline changes.

Each provider reports `availability()` so the dashboard dropdown can show
which options are actually usable right now instead of failing on submit.
"""
from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod

import requests

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class ProviderError(RuntimeError):
    pass


class LLMProvider(ABC):
    key: str = ""
    label: str = ""
    setup_hint: str = ""

    def __init__(self, model: str):
        self.model = model

    @abstractmethod
    def complete(self, system: str, user: str) -> str: ...

    @abstractmethod
    def availability(self) -> tuple[bool, str]:
        """(ready, human-readable reason)."""

    def complete_json(self, system: str, user: str):
        raw = self.complete(system, user)
        cleaned = _FENCE.sub("", raw).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            start, end = cleaned.find("["), cleaned.rfind("]")
            if start == -1:
                start, end = cleaned.find("{"), cleaned.rfind("}")
            if start != -1 and end > start:
                return json.loads(cleaned[start:end + 1])
            raise ProviderError(f"{self.key}: response was not JSON:\n{cleaned[:400]}")


class GeminiProvider(LLMProvider):
    key = "gemini"
    label = "Google Gemini (AI Studio)"
    setup_hint = "Set GEMINI_API_KEY — free key at aistudio.google.com/apikey"
    ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def availability(self):
        return (True, "ready") if os.getenv("GEMINI_API_KEY") else (False, self.setup_hint)

    def complete(self, system, user):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ProviderError(self.setup_hint)
        resp = requests.post(
            self.ENDPOINT.format(model=self.model),
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
            },
            timeout=120,
        )
        if resp.status_code != 200:
            raise ProviderError(f"gemini {resp.status_code}: {resp.text[:300]}")
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


class GroqProvider(LLMProvider):
    key = "groq"
    label = "Groq"
    setup_hint = "Set GROQ_API_KEY — free key at console.groq.com/keys"
    ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

    def availability(self):
        return (True, "ready") if os.getenv("GROQ_API_KEY") else (False, self.setup_hint)

    def complete(self, system, user):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ProviderError(self.setup_hint)
        resp = requests.post(
            self.ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": self.model,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=120,
        )
        if resp.status_code != 200:
            raise ProviderError(f"groq {resp.status_code}: {resp.text[:300]}")
        return resp.json()["choices"][0]["message"]["content"]


class OllamaProvider(LLMProvider):
    key = "ollama"
    label = "Ollama (local)"
    setup_hint = "Start Ollama and pull a model: `ollama pull llama3.1:8b`"
    HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    def availability(self):
        try:
            resp = requests.get(f"{self.HOST}/api/tags", timeout=3)
            names = [m["name"] for m in resp.json().get("models", [])]
            if not names:
                return False, "Ollama is running but has no models pulled"
            if self.model not in names:
                return False, f"Model {self.model} not pulled (have: {', '.join(names[:3])})"
            return True, "ready"
        except Exception:
            return False, f"No Ollama at {self.HOST}"

    def complete(self, system, user):
        resp = requests.post(
            f"{self.HOST}/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.2},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=300,
        )
        if resp.status_code != 200:
            raise ProviderError(f"ollama {resp.status_code}: {resp.text[:300]}")
        return resp.json()["message"]["content"]


REGISTRY: dict[str, type[LLMProvider]] = {
    p.key: p for p in (GeminiProvider, GroqProvider, OllamaProvider)
}


def get_provider(key: str, models: dict[str, str]) -> LLMProvider:
    if key not in REGISTRY:
        raise ProviderError(f"Unknown provider '{key}'. Choose from: {', '.join(REGISTRY)}")
    return REGISTRY[key](models.get(key, ""))


def provider_status(models: dict[str, str]) -> list[dict]:
    """Everything the dropdown needs to render itself."""
    out = []
    for key, cls in REGISTRY.items():
        p = cls(models.get(key, ""))
        ready, reason = p.availability()
        out.append({"key": key, "label": p.label, "model": p.model,
                    "ready": ready, "reason": reason})
    return out
