from __future__ import annotations

import json
import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)


class ModelProvider:
    """
    Proveedor híbrido: Ollama local para modelos pequeños, Groq/OpenRouter para modelos pesados.
    """

    @staticmethod
    def _provider() -> str:
        provider = os.getenv("AI_PROVIDER", "ollama").lower()
        if provider not in {"ollama", "groq", "openrouter"}:
            raise ValueError("AI_PROVIDER inválido. Usa: ollama, groq, openrouter.")
        return provider

    @staticmethod
    def _ollama_url() -> str:
        return os.getenv("OLLAMA_URL", "http://ollama:11434").rstrip("/")

    @staticmethod
    def _ollama_generate(model: str, prompt: str, *, system: str | None = None) -> str:
        url = f"{ModelProvider._ollama_url()}/api/generate"
        payload = {"model": model, "prompt": prompt, "stream": False}
        if system:
            payload["system"] = system
        res = requests.post(url, json=payload, timeout=120)
        res.raise_for_status()
        return res.json().get("response", "").strip()

    @staticmethod
    def _groq_generate(model: str, prompt: str, *, system: str | None = None) -> str:
        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key:
            return "{}"
        url = "https://api.groq.com/openai/v1/chat/completions"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        res = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "messages": messages, "temperature": 0},
            timeout=120,
        )
        res.raise_for_status()
        return res.json()["choices"][0]["message"]["content"]

    @staticmethod
    def _openrouter_generate(model: str, prompt: str, *, system: str | None = None) -> str:
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        if not api_key:
            return "{}"
        url = "https://openrouter.ai/api/v1/chat/completions"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        res = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "messages": messages, "temperature": 0},
            timeout=120,
        )
        res.raise_for_status()
        return res.json()["choices"][0]["message"]["content"]

    @staticmethod
    def generate(model: str, prompt: str, *, system: str | None = None) -> str:
        provider = ModelProvider._provider()
        if provider == "ollama":
            return ModelProvider._ollama_generate(model, prompt, system=system)
        if provider == "groq":
            return ModelProvider._groq_generate(model, prompt, system=system)
        if provider == "openrouter":
            return ModelProvider._openrouter_generate(model, prompt, system=system)
        return "{}"

    @staticmethod
    def extract_json(model: str, prompt: str, *, system: str | None = None) -> dict[str, Any]:
        raw = ModelProvider.generate(model, prompt, system=system)
        try:
            return json.loads(raw)
        except Exception:
            logger.warning("Respuesta no parseable: %s", raw)
            return {}
