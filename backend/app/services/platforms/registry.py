# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Platform registry — import-time ``@register`` decorator + lookup helpers.

The registry is a flat list populated at package import time. No platform
knows about any other platform; detection order is determined solely by each
platform's own ``priority`` attribute (higher wins, ties broken by
registration order which is alphabetical via ``__init__.py`` imports).
"""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

import structlog

from app.services.platforms.base import Platform

logger = structlog.get_logger(__name__)

_PLATFORMS: list[Platform] = []

_PlatformClass = TypeVar("_PlatformClass", bound=type[Platform])


# Ruff prefers PEP 695 `def register[T: type[Platform]](cls: T) -> T` syntax,
# but the ambient mypy (anaconda base) does not yet support it. Keep the
# legacy TypeVar form until the CI mypy is upgraded.
def register(cls: _PlatformClass) -> _PlatformClass:  # noqa: UP047
    """Decorator: instantiate the platform class and add it to the registry."""
    instance = cls()
    _PLATFORMS.append(instance)
    return cls


def all_platforms() -> list[Platform]:
    """Return platforms sorted by priority (highest first), slug-tiebroken.

    Secondary sort by ``slug`` makes ordering deterministic regardless of
    import sequence. Relying on Python's sort stability plus alphabetical
    ``__init__.py`` imports was previously sufficient, but one copy-paste
    error in that file would have silently reshuffled detection for
    equal-priority platforms — an unmissable latent bug class. Explicit
    tiebreak eliminates it.
    """
    return sorted(_PLATFORMS, key=lambda p: (-p.priority, p.slug))


def get_platform(slug: str) -> Platform:
    """Resolve a platform by its slug.

    Raises:
        KeyError: if no registered platform matches the slug.
    """
    for p in _PLATFORMS:
        if p.slug == slug:
            return p
    raise KeyError(f"Unknown platform slug: {slug!r}")


def detect_platform(repo: Path) -> Platform | None:
    """Classify a repository by its UI / frontend toolchain.

    Iterates registered platforms in priority order and returns the first
    match. Returns ``None`` only if the registry itself is empty; the
    ``backend_fallback`` platform matches every non-UI repo, so production
    code always receives a concrete result.

    I/O and decoding errors raised by ``detect()`` are logged at debug and
    treated as a non-match so a single unreadable file cannot block detection
    of later platforms. Other exceptions propagate — they indicate a bug in
    a platform implementation.
    """
    for platform in all_platforms():
        try:
            if platform.detect(repo):
                return platform
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            logger.debug(
                "platform_detect_error",
                platform_slug=platform.slug,
                repo=str(repo),
                error=str(exc),
            )
    return None
