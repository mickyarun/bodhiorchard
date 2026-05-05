# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Shared helpers for formatting feature content + inline embedding.

Used by both the synthesis MCP handler (legacy) and the merge writer
that promotes synth rows to ``knowledge_items``. Lifted out of
``app/mcp/handlers_knowledge.py`` so the merge writer (a service) does
not import from the MCP layer.
"""

from __future__ import annotations

import structlog

from app.services.embedding_service import embedding_service

logger = structlog.get_logger(__name__)


def format_feature_content(
    description: str,
    capabilities: list[str],
    source_clusters: list[str],
    *,
    feature_status: str | None = None,
    source_ref: str | None = None,
) -> str:
    """Format structured feature content for storage.

    Produces a lean plain-text block optimized for embedding search
    (description dominates vector), triage agent reading (capabilities),
    and token efficiency (~100-150 tokens).

    Code locations are stored on the junction table (knowledge_to_repo),
    not in the content text.

    Args:
        description: 1-2 sentence business description.
        capabilities: List of specific things the feature does.
        source_clusters: Cluster names (kept for signature compat).
        feature_status: Optional lifecycle status (planned/in_progress/implemented).
        source_ref: Optional BUD reference (e.g. "BUD-042").

    Returns:
        Formatted plain-text content string.
    """
    lines = [description, ""]

    if feature_status:
        status_label = feature_status.upper().replace("_", " ")
        lines.append(f"Status: {status_label}")
        if source_ref and feature_status != "implemented":
            lines.append(f"Source: {source_ref}")
        lines.append("")

    if capabilities:
        lines.append("Capabilities:")
        for cap in capabilities:
            lines.append(f"- {cap}")

    return "\n".join(lines)


async def try_embed(title: str, content: str) -> list[float] | None:
    """Attempt to embed a feature inline. Returns None on failure."""
    try:
        return await embedding_service.embed(f"{title}\n{content}"[:4000])
    except Exception as exc:
        logger.warning("inline_embed_failed", title=title, error=str(exc))
        return None
