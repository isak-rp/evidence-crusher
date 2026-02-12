"""Embeddings service with Ollama backend."""

from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)


class EmbeddingService:
    _ollama_url: str | None = None
    _ollama_model: str | None = None

    @classmethod
    def _get_ollama_config(cls) -> tuple[str, str]:
        if cls._ollama_url is None:
            cls._ollama_url = os.getenv("OLLAMA_URL", "http://ollama:11434")
        if cls._ollama_model is None:
            cls._ollama_model = os.getenv("OLLAMA_EMBED_MODEL", "mxbai-embed-large")
        return cls._ollama_url, cls._ollama_model

    @classmethod
    def _embed_with_ollama(cls, text: str) -> list[float]:
        ollama_url, model = cls._get_ollama_config()
        endpoints = [
            (f"{ollama_url.rstrip('/')}/api/embed", {"model": model, "input": text}),
            (f"{ollama_url.rstrip('/')}/api/embeddings", {"model": model, "prompt": text}),
        ]
        errors: list[str] = []
        for endpoint, payload in endpoints:
            try:
                response = requests.post(endpoint, json=payload, timeout=30)
                response.raise_for_status()
                data = response.json()
                if "embedding" in data and data["embedding"]:
                    return data["embedding"]
                if "embeddings" in data and data["embeddings"]:
                    return data["embeddings"][0]
            except Exception as exc:
                detail = str(exc)
                if isinstance(exc, requests.HTTPError) and exc.response is not None:
                    body = exc.response.text[:300]
                    detail = f"HTTP {exc.response.status_code} at {endpoint}: {body}"
                errors.append(detail)
                continue
        message = " | ".join(errors) if errors else "No se pudo generar embedding."
        logger.error("Error generando embedding con Ollama: %s", message)
        raise RuntimeError(message)

    @classmethod
    def generate_embedding(cls, text: str) -> list[float]:
        """Genera el vector para un texto dado."""
        try:
            return cls._embed_with_ollama(text)
        except Exception as exc:
            logger.error("Error generando embedding: %s", exc)
            raise
