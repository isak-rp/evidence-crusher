from __future__ import annotations

import json
import logging
import os
import time
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
        started = time.perf_counter()
        url = f"{ModelProvider._ollama_url()}/api/generate"
        payload = {"model": model, "prompt": prompt, "stream": False}
        if system:
            payload["system"] = system
        res = requests.post(url, json=payload, timeout=120)
        res.raise_for_status()
        data = res.json()
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "llm_call provider=ollama model=%s latency_ms=%s eval_count=%s prompt_eval_count=%s",
            model,
            elapsed_ms,
            data.get("eval_count"),
            data.get("prompt_eval_count"),
        )
        return data.get("response", "").strip()

    @staticmethod
    def _groq_generate(model: str, prompt: str, *, system: str | None = None) -> str:
        started = time.perf_counter()
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
        data = res.json()
        usage = data.get("usage", {})
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "llm_call provider=groq model=%s latency_ms=%s prompt_tokens=%s completion_tokens=%s total_tokens=%s",
            model,
            elapsed_ms,
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
            usage.get("total_tokens"),
        )
        return data["choices"][0]["message"]["content"]

    @staticmethod
    def _openrouter_generate(model: str, prompt: str, *, system: str | None = None) -> str:
        started = time.perf_counter()
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
        data = res.json()
        usage = data.get("usage", {})
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "llm_call provider=openrouter model=%s latency_ms=%s prompt_tokens=%s completion_tokens=%s total_tokens=%s",
            model,
            elapsed_ms,
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
            usage.get("total_tokens"),
        )
        return data["choices"][0]["message"]["content"]

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
        retries = max(int(os.getenv("LLM_JSON_RETRIES", "2")), 1)
        for attempt in range(1, retries + 1):
            forced_json_system = (
                f"{system}\n\nDevuelve unicamente JSON valido, sin markdown ni texto extra."
                if system
                else "Devuelve unicamente JSON valido, sin markdown ni texto extra."
            )
            raw = ModelProvider.generate(model, prompt, system=forced_json_system)
            parsed = ModelProvider._parse_json_response(raw)
            if isinstance(parsed, dict):
                return parsed
            logger.warning(
                "Respuesta no parseable (intento %s/%s): %s",
                attempt,
                retries,
                raw[:300],
            )
        return {}

    @staticmethod
    def _parse_json_response(raw: str) -> dict[str, Any] | None:
        if not raw:
            return None
        # Camino rapido: JSON directo.
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        # Recupera el primer objeto JSON valido incrustado dentro de texto/markdown.
        decoder = json.JSONDecoder()
        for idx, ch in enumerate(raw):
            if ch != "{":
                continue
            try:
                obj, _ = decoder.raw_decode(raw[idx:])
                if isinstance(obj, dict):
                    return obj
            except Exception:
                continue
        return None
