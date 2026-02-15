from __future__ import annotations

import os
from typing import Any

from app.core.ai_provider import ModelProvider


class LLMService:
    EXPECTED_EXTRACTION_KEYS = (
        "start_date",
        "end_date",
        "daily_salary",
        "start_date_source_doc_id",
        "end_date_source_doc_id",
        "daily_salary_source_doc_id",
    )

    @staticmethod
    def _provider() -> str:
        return os.getenv("AI_PROVIDER", "ollama").lower()

    @staticmethod
    def _extract_model() -> str:
        if LLMService._provider() == "groq":
            return os.getenv("GROQ_EXTRACT_MODEL", "llama-3.3-70b-versatile")
        return os.getenv("OPENROUTER_EXTRACT_MODEL", "openrouter/auto")

    @staticmethod
    def _rag_model() -> str:
        if LLMService._provider() == "groq":
            return os.getenv("GROQ_RAG_MODEL", "llama-3.1-8b-instant")
        return os.getenv("OPENROUTER_RAG_MODEL", "openrouter/auto")

    @staticmethod
    def _audit_model() -> str:
        if LLMService._provider() == "groq":
            return os.getenv("GROQ_AUDIT_MODEL", "llama-3.3-70b-versatile")
        return os.getenv("OPENROUTER_AUDIT_MODEL", "openrouter/auto")

    @staticmethod
    def current_provider() -> str:
        return LLMService._provider()

    @staticmethod
    def current_extract_model() -> str:
        return LLMService._extract_model()

    @staticmethod
    def classify_with_llama(text: str) -> str:
        system = (
            "Eres un clasificador legal. Devuelve SOLO una etiqueta exacta de la taxonomia "
            "o 'REVISION_REQUERIDA' si no aplica."
        )
        prompt = (
            "Texto:\n"
            f"{text[:4000]}\n\n"
            "Etiqueta exacta:"
        )
        model = os.getenv("OLLAMA_LLM_MODEL", "llama3.2:1b")
        return ModelProvider.generate(model, prompt, system=system)

    @staticmethod
    def extract_structured(text: str) -> dict[str, Any]:
        system = (
            "Eres un extractor legal. Devuelve SOLO JSON valido con las claves: "
            "start_date, end_date, daily_salary, start_date_source_doc_id, end_date_source_doc_id, "
            "daily_salary_source_doc_id. Usa null si no esta."
        )
        prompt = f"Texto:\n{text[:4000]}\n\nJSON:"
        payload = ModelProvider.extract_json(LLMService._extract_model(), prompt, system=system)
        return LLMService._normalize_extraction_payload(payload)

    @staticmethod
    def rag_answer(question: str, context: str) -> str:
        system = "Responde con citas textuales y referencias claras."
        prompt = f"Contexto:\n{context}\n\nPregunta:\n{question}\n\nRespuesta:"
        return ModelProvider.generate(LLMService._rag_model(), prompt, system=system)

    @staticmethod
    def audit_inconsistencies(context: str) -> str:
        system = "Detecta inconsistencias legales entre documentos. Devuelve JSON con items."
        prompt = f"Documentos:\n{context}\n\nJSON:"
        return ModelProvider.generate(LLMService._audit_model(), prompt, system=system)

    @staticmethod
    def _normalize_extraction_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        source = payload or {}
        for key in LLMService.EXPECTED_EXTRACTION_KEYS:
            value = source.get(key)
            normalized[key] = value if value not in ("", "null", "None") else None
        return normalized
