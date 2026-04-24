# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Electron platform detection.

Marker: ``electron`` listed in ``package.json`` deps. Electron apps are "a web
app in a Chromium shell", so the design-token sources are web patterns.
"""

from __future__ import annotations

from pathlib import Path

from app.services.platforms._npm import package_has_any_dep
from app.services.platforms.base import DEFAULT_COMMON_GLOBS, PlatformKind
from app.services.platforms.registry import register

_DEPS: frozenset[str] = frozenset({"electron"})


@register
class ElectronPlatform:
    slug = "electron"
    kind = PlatformKind.DESKTOP
    priority = 60

    def detect(self, repo: Path) -> bool:
        return package_has_any_dep(repo, _DEPS)

    @property
    def design_globs(self) -> tuple[str, ...]:
        # Electron's renderer is a web app. Scope to theme / style files,
        # not every TypeScript file under ``src/renderer/`` (which would
        # include every React/Vue component).
        return DEFAULT_COMMON_GLOBS + (
            "package.json",
            # Theme modules
            "src/**/theme.ts",
            "src/**/theme.tsx",
            "src/**/theme.js",
            "src/**/theme_*.ts",
            "src/**/*_theme.ts",
            "electron/theme.ts",
            # Global stylesheets (explicit names only)
            "src/**/global.css",
            "src/**/global.scss",
            "src/**/main.css",
            "src/**/main.scss",
            "src/**/variables.css",
            "src/**/variables.scss",
            "src/**/tokens.css",
            "src/**/tokens.scss",
            # Tailwind + MUI
            "tailwind.config.*",
            "**/createTheme.*",
            "**/palette.*",
        )

    @property
    def skip_dirs(self) -> tuple[str, ...]:
        return ("out", "release", "dist_electron")

    @property
    def prompt_hint(self) -> str:
        return (
            "Target: Electron desktop app (Chromium web runtime). Extract "
            "design tokens from the renderer process — same conventions as "
            "a web SPA. Flag any native-menu / tray-icon colours declared "
            "in the main process config."
        )
