# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Ionic platform detection.

Marker: ``ionic.config.json`` at repo root. The CLI creates this for every
Ionic project regardless of the UI framework variant (React / Angular / Vue).
"""

from __future__ import annotations

from pathlib import Path

from app.services.platforms.base import DEFAULT_COMMON_GLOBS, PlatformKind
from app.services.platforms.registry import register


@register
class IonicPlatform:
    slug = "ionic"
    kind = PlatformKind.MOBILE_CROSS
    priority = 70

    def detect(self, repo: Path) -> bool:
        return (repo / "ionic.config.json").exists()

    @property
    def design_globs(self) -> tuple[str, ...]:
        return DEFAULT_COMMON_GLOBS + (
            "ionic.config.json",
            "src/theme/variables.css",
            "src/theme/variables.scss",
            "src/theme/**/*.css",
            "src/theme/**/*.scss",
            "src/global.css",
            "src/global.scss",
            "package.json",
        )

    @property
    def skip_dirs(self) -> tuple[str, ...]:
        return ("www", ".ionic", "platforms", "plugins")

    @property
    def prompt_hint(self) -> str:
        return (
            "Target: Ionic hybrid mobile app. Extract design tokens from "
            "`src/theme/variables.css` (the canonical Ionic theme file) and "
            "global stylesheets. Preserve Ionic CSS custom-property naming "
            "(e.g. `--ion-color-primary`)."
        )
