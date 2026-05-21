# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Hybrid keyword + semantic search behaviour for ``get_features``.

Pin the four invariants the code-review pass surfaced:

1. Keyword hit short-circuits — semantic is NOT called when the
   title-substring path already returned rows. (Performance + audit
   trail — embed service should only fire on a real miss.)
2. Keyword miss at offset=0 falls back to semantic and reports
   ``search_mode="semantic"``.
3. Semantic failure (embed crash, model load error) is OBSERVABLE via
   ``search_mode="semantic_failed"`` — without this an admin can't tell
   "no features matched" from "the embedder is down".
4. The handler rejects 1- and 2-char queries with a clear error rather
   than running an ``ILIKE '%a%'`` that would match every title.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.mcp.handlers_features import handle_get_features
from app.repositories.feature_reads import FeatureReadRepository


def _fake_feature(title: str = "Feature: Demo") -> MagicMock:
    """Return a Feature-shaped mock with the columns the handler reads."""
    return MagicMock(
        id=uuid.uuid4(),
        feature_title=title,
        description="demo description",
        capabilities=None,
        tags=[],
        source="scan",
        source_ref=None,
        feature_status="implemented",
    )


@pytest.mark.asyncio
async def test_keyword_hit_short_circuits_semantic(monkeypatch: Any) -> None:
    """When ILIKE returns rows, the embed service must NOT be called."""
    embed_called = False

    async def _embed_should_not_be_called(*a: Any, **kw: Any) -> list[float]:
        nonlocal embed_called
        embed_called = True
        return [0.0] * 384

    async def _keyword_returns_rows(self: Any, query: str, **kw: Any) -> list[Any]:
        return [_fake_feature("Feature: Payment Links")]

    monkeypatch.setattr(FeatureReadRepository, "keyword_search", _keyword_returns_rows)
    monkeypatch.setattr(
        "app.mcp.handlers_features.embedding_service.embed", _embed_should_not_be_called
    )

    org = MagicMock(id=uuid.uuid4())
    result = await handle_get_features(MagicMock(), org, {"query": "payment links"})

    assert result["search_mode"] == "keyword"
    assert len(result["results"]) == 1
    assert embed_called is False, "embed_service must not run on keyword hit"


@pytest.mark.asyncio
async def test_keyword_miss_falls_back_to_semantic(monkeypatch: Any) -> None:
    """When keyword returns empty AND offset=0, semantic fires and
    ``search_mode`` flips to ``"semantic"``."""

    async def _keyword_empty(self: Any, query: str, **kw: Any) -> list[Any]:
        return []

    async def _embed_ok(*a: Any, **kw: Any) -> list[float]:
        return [0.0] * 384

    async def _semantic_returns_rows(self: Any, vector: Any, **kw: Any) -> list[Any]:
        return [(_fake_feature("Feature: Payment Links"), 0.25)]

    monkeypatch.setattr(FeatureReadRepository, "keyword_search", _keyword_empty)
    monkeypatch.setattr(FeatureReadRepository, "semantic_search", _semantic_returns_rows)
    monkeypatch.setattr("app.mcp.handlers_features.embedding_service.embed", _embed_ok)

    org = MagicMock(id=uuid.uuid4())
    result = await handle_get_features(
        MagicMock(), org, {"query": "payment link notes post-payment edit"}
    )

    assert result["search_mode"] == "semantic"
    assert len(result["results"]) == 1
    # Semantic page is single — must not advertise pagination past it.
    assert result["has_more"] is False
    assert result["next_offset"] is None


@pytest.mark.asyncio
async def test_semantic_failure_is_observable(monkeypatch: Any) -> None:
    """Embed crashing must produce ``search_mode="semantic_failed"`` so
    admin tooling can distinguish "no matches" from "embedder is down"."""

    async def _keyword_empty(self: Any, query: str, **kw: Any) -> list[Any]:
        return []

    async def _embed_raises(*a: Any, **kw: Any) -> list[float]:
        raise RuntimeError("fastembed model unavailable")

    monkeypatch.setattr(FeatureReadRepository, "keyword_search", _keyword_empty)
    monkeypatch.setattr("app.mcp.handlers_features.embedding_service.embed", _embed_raises)

    org = MagicMock(id=uuid.uuid4())
    result = await handle_get_features(MagicMock(), org, {"query": "anything"})

    assert result["search_mode"] == "semantic_failed"
    assert result["results"] == []


@pytest.mark.asyncio
async def test_short_query_rejected_with_clear_error() -> None:
    """``%a%`` would match every title — reject sub-3 with an explicit error."""
    org = MagicMock(id=uuid.uuid4())
    for short in ("a", "ab", "  ab  "):
        result = await handle_get_features(MagicMock(), org, {"query": short})
        assert result["results"] == []
        assert "3 characters" in result["error"], f"query={short!r}: {result!r}"


@pytest.mark.asyncio
async def test_empty_query_rejected() -> None:
    """Sanity: missing / whitespace-only query rejected separately from short queries."""
    org = MagicMock(id=uuid.uuid4())
    for bad in ("", "   ", None):
        params: dict[str, Any] = {"query": bad} if bad is not None else {}
        result = await handle_get_features(MagicMock(), org, params)
        assert result["error"] == "query is required"
