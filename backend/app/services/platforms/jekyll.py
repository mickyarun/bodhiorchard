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

"""Jekyll static site detection.

Markers: ``_config.yml`` AND one of ``_sass/`` or ``_layouts/``. The YAML
file alone is ambiguous (many tools use ``_config.yml``); requiring the
Jekyll-specific directories distinguishes this from, say, MkDocs.
"""

from __future__ import annotations

from pathlib import Path

from app.services.platforms.base import DEFAULT_COMMON_GLOBS, PlatformKind
from app.services.platforms.registry import register


@register
class JekyllPlatform:
    slug = "jekyll"
    kind = PlatformKind.STATIC_SITE
    priority = 50

    def detect(self, repo: Path) -> bool:
        if not (repo / "_config.yml").exists():
            return False
        return (repo / "_sass").is_dir() or (repo / "_layouts").is_dir()

    @property
    def design_globs(self) -> tuple[str, ...]:
        return DEFAULT_COMMON_GLOBS + (
            "_config.yml",
            "_sass/**/*.scss",
            "_sass/**/*.sass",
            "assets/css/**/*.scss",
            "assets/css/**/*.css",
            "_includes/theme/**/*.html",
        )

    @property
    def skip_dirs(self) -> tuple[str, ...]:
        return ("_site", ".jekyll-cache")

    @property
    def prompt_hint(self) -> str:
        return (
            "Target: Jekyll static site. Extract design tokens from "
            "`_sass/` variables and any SCSS under `assets/css/`. Preserve "
            "SCSS variable names (e.g. ``$brand-primary``) as they often "
            "double as the site's public token interface."
        )
