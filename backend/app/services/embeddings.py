"""Local embeddings service using sentence-transformers."""

from __future__ import annotations

import logging

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class EmbeddingService:
    _model: SentenceTransformer | None = None

    @classmethod
    def get_model(cls) -> SentenceTransformer:
        """Singleton: load the model only once."""
        if cls._model is None:
            logger.info("Cargando modelo de Embeddings (all-MiniLM-L6-v2)...")
            cls._model = SentenceTransformer("all-MiniLM-L6-v2")
        return cls._model

    @classmethod
    def generate_embedding(cls, text: str) -> list[float]:
        """Genera el vector para un texto dado."""
        try:
            model = cls.get_model()
            embedding = model.encode(text).tolist()
            return embedding
        except Exception as exc:
            logger.error("Error generando embedding: %s", exc)
            raise
