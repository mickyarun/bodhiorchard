# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Generic web JS/TS platform.

Detection: ``package.json`` with at least one dependency in
:attr:`WebJsPlatform.dependencies`. This covers frameworks with no
platform-specific detector (Vue, React, Svelte, Astro, Solid, Qwik, …). More
specialized JS platforms (React Native, Expo, Electron, Tauri, Ionic, …)
register at higher priority and claim their repos first.
"""

from __future__ import annotations

from pathlib import Path

from app.services.platforms._npm import package_has_any_dep
from app.services.platforms.base import DEFAULT_COMMON_GLOBS, PlatformKind
from app.services.platforms.registry import register


@register
class WebJsPlatform:
    slug = "web_js"
    kind = PlatformKind.WEB
    priority = 30

    # Frameworks and design-token libraries whose presence marks a repo as a
    # web frontend. More specialized JS platforms (React Native, Expo, Electron,
    # Ionic, …) register their own modules at higher priority.
    dependencies: frozenset[str] = frozenset(
        {
            # Core SPA frameworks
            "vue",
            "react",
            "react-dom",
            "preact",
            "@angular/core",
            "svelte",
            "@sveltejs/kit",
            "solid-js",
            "@builder.io/qwik",
            "lit",
            "@stencil/core",
            # Meta-frameworks / SSR / SSG
            "next",
            "nuxt",
            "astro",
            "@remix-run/react",
            "gatsby",
            "@11ty/eleventy",
            "ember-source",
            # Hypermedia / sprinkles
            "alpinejs",
            # Design-system / styling libraries
            "vuetify",
            "@mui/material",
            "tailwindcss",
        }
    )

    def detect(self, repo: Path) -> bool:
        return package_has_any_dep(repo, self.dependencies)

    @property
    def design_globs(self) -> tuple[str, ...]:
        return DEFAULT_COMMON_GLOBS + (
            "package.json",
            # Vuetify / Vue config
            "**/vuetify.ts",
            "**/vuetify.js",
            "**/vuetify.config.*",
            # Theme / style files
            "**/theme.ts",
            "**/theme.js",
            "**/theme.config.*",
            "**/themes/**/*.ts",
            "**/themes/**/*.js",
            # CSS / SCSS / SASS
            "**/main.scss",
            "**/main.css",
            "**/variables.scss",
            "**/variables.css",
            "**/tokens.scss",
            "**/tokens.css",
            "**/global.scss",
            "**/global.css",
            # Tailwind
            "tailwind.config.*",
            "**/tailwind.config.*",
            # MUI
            "**/createTheme.*",
            "**/palette.*",
        )

    @property
    def skip_dirs(self) -> tuple[str, ...]:
        return ()

    @property
    def prompt_hint(self) -> str:
        return (
            "Target: web application (JavaScript/TypeScript). Extract "
            "design tokens from the framework's idiomatic theme files "
            "(Vuetify theme, Tailwind config, MUI createTheme, CSS custom "
            "properties). Output CDN boilerplate if the framework ships one."
        )
