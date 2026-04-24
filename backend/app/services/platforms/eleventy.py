# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Eleventy (11ty) static site detection.

Markers: ``.eleventy.js`` or ``eleventy.config.(js|ts|cjs|mjs)`` OR
``package.json`` listing ``@11ty/eleventy`` (already also caught by
``web_js``, but we pin it here for richer globs / prompt).
"""

from __future__ import annotations

from pathlib import Path

from app.services.platforms._npm import package_has_any_dep
from app.services.platforms.base import DEFAULT_COMMON_GLOBS, PlatformKind
from app.services.platforms.registry import register

_CONFIG_CANDIDATES: tuple[str, ...] = (
    ".eleventy.js",
    "eleventy.config.js",
    "eleventy.config.cjs",
    "eleventy.config.mjs",
    "eleventy.config.ts",
)


@register
class EleventyPlatform:
    slug = "eleventy"
    kind = PlatformKind.STATIC_SITE
    priority = 50

    def detect(self, repo: Path) -> bool:
        if any((repo / c).exists() for c in _CONFIG_CANDIDATES):
            return True
        return package_has_any_dep(repo, frozenset({"@11ty/eleventy"}))

    @property
    def design_globs(self) -> tuple[str, ...]:
        return DEFAULT_COMMON_GLOBS + (
            ".eleventy.js",
            "eleventy.config.*",
            "src/_includes/css/**/*",
            "src/_includes/sass/**/*",
            "src/assets/css/**/*",
            "src/assets/scss/**/*",
            "package.json",
        )

    @property
    def skip_dirs(self) -> tuple[str, ...]:
        return ("_site",)

    @property
    def prompt_hint(self) -> str:
        return (
            "Target: Eleventy (11ty) static site. Extract design tokens "
            "from SCSS / CSS under `src/_includes/` or `src/assets/`. "
            "Eleventy is templating-agnostic, so token sources live in the "
            "plain stylesheet files rather than framework theme configs."
        )
