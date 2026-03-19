"""Embedding service for generating vector representations of text."""

from typing import Any

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)


class EmbeddingService:
    """Text embedding service supporting multiple providers.

    Supported providers: ollama, openai, sentence-transformers.
    """

    def __init__(self) -> None:
        self._provider = settings.embedding.provider
        self._model = settings.embedding.model
        self._dimensions = settings.embedding.dimensions

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

        Args:
            texts: List of texts to embed.

        Returns:
            A list of embedding vectors, one per input text.

        Raises:
            ValueError: If the configured provider is unsupported.
        """
        if self._provider == "ollama":
            return await self._embed_ollama(texts)
        elif self._provider == "openai":
            return await self._embed_openai(texts)
        elif self._provider == "sentence-transformers":
            return await self._embed_sentence_transformers(texts)
        else:
            raise ValueError(f"Unsupported embedding provider: {self._provider}")

    async def _embed_ollama(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings via the Ollama REST API.

        Uses the /api/embed endpoint (Ollama 0.1.26+) which supports batch input natively.

        Args:
            texts: List of texts to embed.

        Returns:
            A list of embedding vectors.
        """
        base_url = settings.llm.base_url.rstrip("/")

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{base_url}/api/embed",
                json={"model": self._model, "input": texts},
            )
            response.raise_for_status()
            data: dict[str, Any] = response.json()

        logger.info("embed_ollama", count=len(texts), model=self._model)
        return data["embeddings"]

    async def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings via the OpenAI embeddings API.

        Args:
            texts: List of texts to embed.

        Returns:
            A list of embedding vectors.
        """
        import litellm

        response = await litellm.aembedding(
            model=self._model,
            input=texts,
        )

        results: list[list[float]] = [item["embedding"] for item in response.data]  # type: ignore[union-attr]
        logger.info("embed_openai", count=len(texts), model=self._model)
        return results

    async def _embed_sentence_transformers(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using a local sentence-transformers model.

        Loads the model lazily on first call.

        Args:
            texts: List of texts to embed.

        Returns:
            A list of embedding vectors.
        """
        from sentence_transformers import SentenceTransformer

        if not hasattr(self, "_st_model"):
            self._st_model = SentenceTransformer(self._model)

        embeddings = self._st_model.encode(texts, normalize_embeddings=True)
        results = [embedding.tolist() for embedding in embeddings]
        logger.info("embed_sentence_transformers", count=len(texts), model=self._model)
        return results


embedding_service = EmbeddingService()
