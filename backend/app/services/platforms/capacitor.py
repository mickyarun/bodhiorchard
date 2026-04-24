# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Capacitor platform detection.

Marker: ``capacitor.config.(ts|json|js)`` at repo root. Lower priority than
Ionic so an Ionic+Capacitor app classifies as Ionic (richer design context).
"""

from __future__ import annotations

from pathlib import Path

from app.services.platforms.base import DEFAULT_COMMON_GLOBS, PlatformKind
from app.services.platforms.registry import register

_CONFIG_CANDIDATES: tuple[str, ...] = (
    "capacitor.config.ts",
    "capacitor.config.js",
    "capacitor.config.json",
)


@register
class CapacitorPlatform:
    slug = "capacitor"
    kind = PlatformKind.MOBILE_CROSS
    priority = 65

    def detect(self, repo: Path) -> bool:
        return any((repo / c).exists() for c in _CONFIG_CANDIDATES)

    @property
    def design_globs(self) -> tuple[str, ...]:
        # ``src/theme/**/*`` is acceptable — that directory exists only
        # to hold design tokens. But ``src/**/*.css`` would sweep every
        # component stylesheet, so scope the non-``theme/`` CSS matches
        # to global / variables / tokens filenames.
        return DEFAULT_COMMON_GLOBS + (
            "capacitor.config.ts",
            "capacitor.config.js",
            "capacitor.config.json",
            "package.json",
            "src/theme/**/*",
            "src/**/global.css",
            "src/**/global.scss",
            "src/**/variables.css",
            "src/**/variables.scss",
            "src/**/tokens.css",
            "src/**/tokens.scss",
        )

    @property
    def skip_dirs(self) -> tuple[str, ...]:
        return ("ios", "android", "www", "dist")

    @property
    def prompt_hint(self) -> str:
        return (
            "Target: Capacitor web-to-native bridge app. Extract tokens from "
            "the web source (CSS / SCSS / framework theme) plus any "
            "`splashBackgroundColor` / `statusBarStyle` declared in "
            "`capacitor.config.*`."
        )
