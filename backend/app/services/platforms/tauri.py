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

"""Tauri platform detection.

Marker: ``src-tauri/tauri.conf.json`` — Tauri's mandatory configuration file.
The Rust backend lives under ``src-tauri/`` and the UI is any web stack in
``src/``.
"""

from __future__ import annotations

from pathlib import Path

from app.services.platforms.base import DEFAULT_COMMON_GLOBS, PlatformKind
from app.services.platforms.registry import register


@register
class TauriPlatform:
    slug = "tauri"
    kind = PlatformKind.DESKTOP
    priority = 65

    def detect(self, repo: Path) -> bool:
        return (repo / "src-tauri" / "tauri.conf.json").exists()

    @property
    def design_globs(self) -> tuple[str, ...]:
        # Tauri's web UI lives under ``src/`` (same shape as any Vite /
        # Next / SolidStart project). Keep scope tight — dedicated theme
        # folder + globally-named stylesheets, not every CSS file.
        return DEFAULT_COMMON_GLOBS + (
            "src-tauri/tauri.conf.json",
            "src-tauri/Cargo.toml",
            "package.json",
            # Theme modules
            "src/**/theme.ts",
            "src/**/theme.tsx",
            "src/**/theme_*.ts",
            "src/**/*_theme.ts",
            # Dedicated style folders
            "src/styles/**/*.css",
            "src/styles/**/*.scss",
            "src/theme/**/*",
            # Global stylesheets (explicit names)
            "src/**/global.css",
            "src/**/global.scss",
            "src/**/main.css",
            "src/**/main.scss",
            "src/**/variables.css",
            "src/**/variables.scss",
            "src/**/tokens.css",
            "src/**/tokens.scss",
            "tailwind.config.*",
        )

    @property
    def skip_dirs(self) -> tuple[str, ...]:
        return ("src-tauri/target", "src-tauri/gen")

    @property
    def prompt_hint(self) -> str:
        return (
            "Target: Tauri desktop app (Rust backend + web UI). Extract "
            "design tokens from the web UI under `src/` (CSS / SCSS / "
            "framework theme). Note any window-chrome / background colours "
            "declared under the `windows` section of `tauri.conf.json`."
        )
