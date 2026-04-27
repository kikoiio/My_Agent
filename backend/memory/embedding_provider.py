"""Embedding provider with graceful fallback for vector similarity.

Plan.md §7.2.3: BGE-M3 default, can be swapped for OpenAI, Cohere, etc.
Attempts sentence-transformers (local), then OpenAI API, then placeholder.
"""

from __future__ import annotations

import logging
from typing import Any

__all__ = ["EmbeddingProvider"]

logger = logging.getLogger(__name__)

# Prefer local model, then API, then placeholder
_HAS_SENTENCE_TRANSFORMERS = False
_HAS_OPENAI = False
try:
    from sentence_transformers import SentenceTransformer
    _HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    pass

try:
    from openai import AsyncOpenAI
    _HAS_OPENAI = True
except ImportError:
    pass


class EmbeddingProvider:
    """Embedding model with automatic backend selection.

    Priority: local sentence-transformers > OpenAI API > placeholder.
    """

    def __init__(self, model: str = "bge-m3", api_key: str | None = None):
        self.model = model
        self.api_key = api_key
        self._local_model: Any = None
        self._openai_client: Any = None
        self._backend = self._init_backend()

    def _init_backend(self) -> str:
        """Detect and initialize the best available backend."""
        if _HAS_SENTENCE_TRANSFORMERS:
            try:
                model_name = "BAAI/bge-m3" if self.model == "bge-m3" else self.model
                self._local_model = SentenceTransformer(model_name)
                logger.info(f"Embedding: using local model {model_name}")
                return "sentence_transformers"
            except Exception as e:
                logger.warning(f"Failed to load local embedding model: {e}")

        if _HAS_OPENAI and self.api_key:
            try:
                self._openai_client = AsyncOpenAI(api_key=self.api_key)
                logger.info("Embedding: using OpenAI API")
                return "openai"
            except Exception as e:
                logger.warning(f"Failed to init OpenAI client: {e}")

        logger.info("Embedding: using placeholder (dummy vectors)")
        return "placeholder"

    async def embed(self, text: str) -> list[float]:
        """Generate embedding vector for text.

        Returns:
            Vector of floats (dimension depends on model)
        """
        if self._backend == "sentence_transformers" and self._local_model:
            return self._local_model.encode(text).tolist()

        if self._backend == "openai" and self._openai_client:
            try:
                response = await self._openai_client.embeddings.create(
                    model="text-embedding-3-small",
                    input=text,
                )
                return response.data[0].embedding
            except Exception as e:
                logger.error(f"OpenAI embedding failed: {e}")

        return [0.0] * 384

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        if self._backend == "sentence_transformers" and self._local_model:
            return self._local_model.encode(texts).tolist()

        if self._backend == "openai" and self._openai_client:
            try:
                response = await self._openai_client.embeddings.create(
                    model="text-embedding-3-small",
                    input=texts,
                )
                return [d.embedding for d in response.data]
            except Exception as e:
                logger.error(f"OpenAI batch embedding failed: {e}")

        return [await self.embed(text) for text in texts]

    @staticmethod
    def similarity(vec1: list[float], vec2: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not vec1 or not vec2:
            return 0.0
        dot = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = (sum(a * a for a in vec1) ** 0.5) or 1.0
        norm2 = (sum(b * b for b in vec2) ** 0.5) or 1.0
        return dot / (norm1 * norm2)
