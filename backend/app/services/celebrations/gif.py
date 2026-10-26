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

"""Celebratory GIF lookup via the Giphy random endpoint.

Decorative, never load-bearing: every failure path — no API key, a
timeout, a rate limit, a malformed response — returns ``None`` and the
digest goes out text-only. A missing GIF must never cost someone their
birthday post.
"""

from __future__ import annotations

import random
from typing import Any

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

_GIPHY_RANDOM = "https://api.giphy.com/v1/gifs/random"
_TIMEOUT = 6

# Giphy's ``downsized_medium`` is capped at ~5MB, which Slack unfurls
# reliably; the ``original`` can be large enough that Slack skips it.
_RENDITION_ORDER = ("downsized_medium", "downsized", "fixed_height", "original")


async def random_celebration_gif(
    *,
    tags: list[str],
    rating: str = "g",
) -> str | None:
    """Return a GIF URL for a random tag from ``tags``, or ``None``.

    Args:
        tags: Search tags; one is chosen at random so the channel does not
            see the same search every morning.
        rating: Giphy content-rating ceiling (``g``, ``pg``, ``pg-13``).

    Returns:
        A directly embeddable ``.gif`` URL, or ``None`` if the lookup
        failed or is not configured.
    """
    api_key = settings.integrations.giphy_api_key
    if not api_key or not tags:
        return None

    tag = random.choice(tags)  # noqa: S311 — cosmetic choice, not security
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                _GIPHY_RANDOM,
                params={"api_key": api_key, "tag": tag, "rating": rating},
                timeout=_TIMEOUT,
            )
        if resp.status_code != 200:
            logger.warning("giphy_lookup_failed", status=resp.status_code, tag=tag)
            return None
        payload = resp.json()
        # Parsing stays inside the guard: Giphy has answered with
        # ``data: []`` and other shapes, and a GIF must never be able to
        # crash a post — real or sample.
        data = payload.get("data") if isinstance(payload, dict) else None
        return _pick_rendition(data) if isinstance(data, dict) else None
    except Exception:
        logger.warning("giphy_lookup_error", tag=tag, exc_info=True)
        return None


def _pick_rendition(data: dict[str, Any]) -> str | None:
    """Pull the best Slack-friendly rendition URL out of a Giphy payload.

    Giphy returns ``data: []`` (a list, not a dict) when a tag has no
    match, so the shape is checked rather than assumed.
    """
    images = data.get("images")
    if not isinstance(images, dict):
        return None
    for name in _RENDITION_ORDER:
        rendition = images.get(name)
        if not isinstance(rendition, dict):
            continue
        url = rendition.get("url")
        # Strip Giphy's tracking query string so Slack's unfurler sees a
        # plain .gif and renders it inline.
        if isinstance(url, str) and url:
            return url.split("?", 1)[0]
    return None
