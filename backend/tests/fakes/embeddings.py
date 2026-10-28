# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A deterministic stand-in for the fastembed model behind ``embedding_service``.

The real model is downloaded from Hugging Face on first use, which the
guard refuses. :class:`FakeEmbedder` replaces the singleton's ``embed`` /
``embed_batch`` / ``check`` / ``warm`` with a hash-seeded unit vector of the
same 384 dimensions, so equal text gives equal vectors and pgvector
distance queries behave. ``pin()`` fixes the vector for any text containing
a phrase (for threshold tests); ``failing = True`` makes every call raise.
"""

from __future__ import annotations

import hashlib
import math

import pytest

from app.services.embedding_service import embedding_service

DIMENSIONS = 384


def hashed_vector(text: str) -> list[float]:
    """A unit vector derived from ``text`` (same text, same vector)."""
    seed = hashlib.sha256(text.encode()).digest()
    raw = [((seed[i % len(seed)] + i * 31) % 255) / 127.0 - 1.0 for i in range(DIMENSIONS)]
    norm = math.sqrt(sum(v * v for v in raw)) or 1.0
    return [v / norm for v in raw]


class FakeEmbedder:
    """See the module docstring."""

    def __init__(self) -> None:
        self.pinned: dict[str, list[float]] = {}
        self.calls: list[str] = []
        self.failing = False

    def pin(self, phrase: str, vector: list[float]) -> None:
        """Use ``vector`` for any text that contains ``phrase``."""
        assert len(vector) == DIMENSIONS, f"vectors must have {DIMENSIONS} dimensions"
        self.pinned[phrase] = vector

    async def embed(self, text: str) -> list[float]:
        """Vector for one text."""
        self.calls.append(text)
        if self.failing:
            raise RuntimeError("fake embedding failure")
        for phrase, vector in self.pinned.items():
            if phrase in text:
                return list(vector)
        return hashed_vector(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Vectors for many texts."""
        return [await self.embed(text) for text in texts]

    async def check(self) -> tuple[bool, str]:
        """Pre-flight result matching ``EmbeddingService.check``."""
        return (False, "fake embedding failure") if self.failing else (True, "")

    async def warm(self) -> None:
        """No model to load."""

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Swap the methods on the shared ``embedding_service`` singleton."""
        for name in ("embed", "embed_batch", "check", "warm"):
            monkeypatch.setattr(embedding_service, name, getattr(self, name))
