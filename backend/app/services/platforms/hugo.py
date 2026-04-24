# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Hugo static site detection.

Markers: a Hugo config file (``hugo.toml`` / ``hugo.yaml`` / ``config.toml`` /
``config.yaml``) AND a ``content/`` directory (Hugo's canonical content root).
"""

from __future__ import annotations

from pathlib import Path

from app.services.platforms.base import DEFAULT_COMMON_GLOBS, PlatformKind
from app.services.platforms.registry import register

_CONFIG_CANDIDATES: tuple[str, ...] = (
    "hugo.toml",
    "hugo.yaml",
    "hugo.yml",
    "config.toml",
    "config.yaml",
    "config.yml",
)


@register
class HugoPlatform:
    slug = "hugo"
    kind = PlatformKind.STATIC_SITE
    priority = 50

    def detect(self, repo: Path) -> bool:
        if not any((repo / c).exists() for c in _CONFIG_CANDIDATES):
            return False
        return (repo / "content").is_dir()

    @property
    def design_globs(self) -> tuple[str, ...]:
        return DEFAULT_COMMON_GLOBS + (
            "hugo.toml",
            "hugo.yaml",
            "config.toml",
            "config.yaml",
            "assets/scss/**/*.scss",
            "assets/css/**/*.css",
            "themes/*/assets/**/*.scss",
            "themes/*/assets/**/*.css",
            "themes/*/layouts/partials/head.html",
        )

    @property
    def skip_dirs(self) -> tuple[str, ...]:
        return ("public", "resources", ".hugo_build.lock")

    @property
    def prompt_hint(self) -> str:
        return (
            "Target: Hugo static site. Extract design tokens from SCSS / "
            "CSS under `assets/` and any active `themes/*/assets/`. Note "
            "brand colours declared in the Hugo config file (usually under "
            "`params`)."
        )
