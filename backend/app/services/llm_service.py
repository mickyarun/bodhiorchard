"""LLM service for text generation using litellm as a unified interface."""

from typing import Any

import litellm
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)


class LLMService:
    """Unified LLM generation service supporting multiple providers via litellm.

    Supports a default (cost-effective) and premium (high-quality) model tier.
    """

    def __init__(self) -> None:
        self._default_model = self._build_model_name(settings.llm.provider, settings.llm.model)
        self._premium_model = self._build_model_name(
            settings.llm.premium_provider, settings.llm.premium_model
        )
        self._base_url = settings.llm.base_url

    @staticmethod
    def _build_model_name(provider: str, model: str) -> str:
        """Build the litellm model identifier string.

        Args:
            provider: The LLM provider name (e.g., 'ollama', 'openai').
            model: The model name or tag.

        Returns:
            A litellm-compatible model string.
        """
        if provider == "openai":
            return model
        return f"{provider}/{model}"

    async def generate(
        self,
        messages: list[dict[str, str]],
        model_tier: str = "default",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """Generate a text completion from the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            model_tier: Either 'default' or 'premium'.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in the response.
            **kwargs: Additional litellm parameters.

        Returns:
            The generated text content.
        """
        model = self._premium_model if model_tier == "premium" else self._default_model

        logger.info(
            "llm_generate",
            model=model,
            tier=model_tier,
            message_count=len(messages),
        )

        response = await litellm.acompletion(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            api_base=self._base_url if "ollama" in model else None,
            **kwargs,
        )

        content: str = response.choices[0].message.content  # type: ignore[union-attr]

        logger.info(
            "llm_generate_complete",
            model=model,
            usage=getattr(response, "usage", None),
        )

        return content


llm_service = LLMService()
