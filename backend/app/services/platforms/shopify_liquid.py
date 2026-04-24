# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Shopify Liquid theme detection.

Markers:
- ``config/settings_schema.json`` (Shopify theme config schema).
- At least one ``*.liquid`` file under ``templates/``.
"""

from __future__ import annotations

from pathlib import Path

from app.services.platforms.base import DEFAULT_COMMON_GLOBS, PlatformKind
from app.services.platforms.registry import register


@register
class ShopifyLiquidPlatform:
    slug = "shopify_liquid"
    kind = PlatformKind.STATIC_SITE
    priority = 50

    def detect(self, repo: Path) -> bool:
        if not (repo / "config" / "settings_schema.json").exists():
            return False
        return next((repo / "templates").glob("*.liquid"), None) is not None

    @property
    def design_globs(self) -> tuple[str, ...]:
        return DEFAULT_COMMON_GLOBS + (
            "config/settings_schema.json",
            "config/settings_data.json",
            "assets/*.scss",
            "assets/*.css",
            "assets/theme.css",
            "assets/theme.scss",
            "snippets/*.liquid",
        )

    @property
    def skip_dirs(self) -> tuple[str, ...]:
        return ("dist",)

    @property
    def prompt_hint(self) -> str:
        return (
            "Target: Shopify Liquid theme. Extract design tokens from "
            "`config/settings_schema.json` (the merchant-facing theme "
            "settings) and the SCSS/CSS under `assets/`. Preserve the "
            "`settings_schema` section names so merchant-configurable "
            "tokens remain traceable."
        )
