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
    Both model load and inference run on a thread pool so neither blocks the
    asyncio event loop. A per-instance lock serialises the lazy load so
    concurrent first callers don't each pay the ~10s cost.
    """

    def __init__(self) -> None:
        self._model_name: str = settings.embedding.model
        self._model: TextEmbedding | None = None
        # Lazy-init in _load_model so the lock binds to the running event
        # loop, not whichever loop happened to be current at import time.
        # Prevents "attached to a different loop" under pytest-asyncio where
        # each test spins its own loop.
        self._load_lock: asyncio.Lock | None = None

    async def _load_model(self) -> TextEmbedding:
        """Lazy-load the fastembed TextEmbedding model in a worker thread.

        The fastembed import and ONNX model construction together take ~10s
        and are fully synchronous. Running them on the event loop would
        stall every other concurrent request for that window. Double-checked
        locking avoids redundant loads if multiple callers race the first
        hit.
        """
        if self._model is not None:
            return self._model
        if self._load_lock is None:
            self._load_lock = asyncio.Lock()
        async with self._load_lock:
            if self._model is not None:
                return self._model

            def _load() -> TextEmbedding:
                from fastembed import TextEmbedding

                return TextEmbedding(self._model_name)

            self._model = await asyncio.to_thread(_load)
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
        model = await self._load_model()
        results = await asyncio.to_thread(lambda: [v.tolist() for v in model.embed(texts)])
        logger.info("embed_fastembed", count=len(texts), model=self._model_name)
        return results

    async def warm(self) -> None:
        """Eagerly load the model off the event loop.

        Invoked from the app lifespan so the first real ``embed`` call on
        a fresh worker does not pay the ~10s lazy-load cost while other
        requests wait. Safe to call multiple times — the load itself is
        lock-guarded and idempotent.
        """
        await self._load_model()

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
