# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Expo platform detection.

Markers (any one qualifies):
- ``expo`` listed in ``package.json`` deps.
- ``app.json`` with an ``expo:`` top-level key.
- ``app.config.{js,ts}`` at repo root (Expo's dynamic config file).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.platforms._npm import package_has_any_dep
from app.services.platforms.base import DEFAULT_COMMON_GLOBS, PlatformKind
from app.services.platforms.registry import register

_DEPS: frozenset[str] = frozenset({"expo"})


def _app_json_has_expo_key(repo: Path) -> bool:
    app_json = repo / "app.json"
    if not app_json.exists():
        return False
    try:
        data = json.loads(app_json.read_text())
    except (json.JSONDecodeError, OSError):
        return False
    return isinstance(data, dict) and "expo" in data


@register
class ExpoPlatform:
    slug = "expo"
    kind = PlatformKind.MOBILE_CROSS
    priority = 70

    def detect(self, repo: Path) -> bool:
        if package_has_any_dep(repo, _DEPS):
            return True
        if _app_json_has_expo_key(repo):
            return True
        return (repo / "app.config.js").exists() or (repo / "app.config.ts").exists()

    @property
    def design_globs(self) -> tuple[str, ...]:
        # Same Flutter-style discipline: match files by specific names, not
        # by grab-all wildcards. ``src/constants/**/*.ts`` used to sweep in
        # api_endpoints.ts / routes.ts / keys.ts on real apps.
        return DEFAULT_COMMON_GLOBS + (
            "package.json",
            "app.json",
            "app.config.js",
            "app.config.ts",
            # Theme modules (dedicated directories are fine — they exist to
            # hold theme tokens)
            "src/theme/**/*.ts",
            "src/theme/**/*.tsx",
            "src/styles/**/*.ts",
            "src/styles/**/*.tsx",
            # Files named explicitly like tokens / colors / typography
            "**/theme.ts",
            "**/tokens.ts",
            "**/colors.ts",
            "**/typography.ts",
            "**/text_styles.ts",
            "**/design_tokens.ts",
            "**/*_colors.ts",
            "**/*_theme.ts",
        )

    @property
    def skip_dirs(self) -> tuple[str, ...]:
        return (".expo", ".expo-shared")

    @property
    def prompt_hint(self) -> str:
        return (
            "Target: Expo-managed React Native app. Extract design tokens "
            "from the theme module plus any colour/font metadata declared in "
            "`app.json` / `app.config.(js|ts)`. Respect Expo conventions for "
            "splash screens, adaptive icons, and status-bar styling."
        )
