# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Embedding service using fastembed for local, zero-dependency vector generation."""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

# Suppress HuggingFace tokenizers fork warning (fastembed uses ONNX, not PyTorch)
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import structlog

from app.config import settings

if TYPE_CHECKING:
    from fastembed import TextEmbedding

logger = structlog.get_logger(__name__)


class EmbeddingService:
    """Text embedding service using fastembed (ONNX-based, no external service).

    Model is downloaded on first use (~90MB) and cached locally.
    CPU-bound inference is offloaded to a thread pool to avoid blocking asyncio.
    """

    def __init__(self) -> None:
        self._model_name: str = settings.embedding.model
        self._model: TextEmbedding | None = None

    def _get_model(self) -> TextEmbedding:
        """Lazy-load the fastembed TextEmbedding model."""
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(self._model_name)
            logger.info("embedding_model_loaded", model=self._model_name)
        return self._model

    async def embed(self, text: str) -> list[float]:
        """Generate an embedding vector for a single text input.

        Args:
            text: The text to embed.

        Returns:
            A list of floats representing the embedding vector.
        """
        vectors = await self.embed_batch([text])
        return vectors[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for a batch of texts.

        Offloaded to a thread pool so ONNX inference doesn't block the event loop.

        Args:
            texts: List of texts to embed.

        Returns:
            A list of embedding vectors, one per input text.
        """
        model = self._get_model()
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None, lambda: [v.tolist() for v in model.embed(texts)]
        )
        logger.info("embed_fastembed", count=len(texts), model=self._model_name)
        return results

    async def check(self) -> tuple[bool, str]:
        """Test embedding service with a trivial input.

        Returns:
            Tuple of (success, error_message). Error is empty on success.
        """
        try:
            result = await self.embed("test")
            if len(result) > 0:
                return True, ""
            return False, "Empty embedding returned"
        except Exception as e:
            return False, str(e)


embedding_service = EmbeddingService()
