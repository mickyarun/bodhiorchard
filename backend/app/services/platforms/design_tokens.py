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

"""Standalone design-tokens repository detection.

Markers (any one qualifies):
- ``tokens.json`` or ``design-tokens.json`` at repo root (W3C Design Tokens
  Format, Figma-Tokens export, or a hand-written token file).
- A named Style Dictionary config
  (``style-dictionary.config.(js|cjs|mjs|json)``) — the bare ``config.json``
  is intentionally **not** accepted alone, because that filename is too
  generic and produces false positives on Electron, Storybook, and
  random backend repos.
- A Theo config (``theo.config.js``).
- A ``tokens/`` directory with JSON or YAML files at the top level.
"""

from __future__ import annotations

from pathlib import Path

from app.services.platforms.base import DEFAULT_COMMON_GLOBS, PlatformKind
from app.services.platforms.registry import register

_ROOT_TOKEN_FILES: tuple[str, ...] = ("tokens.json", "design-tokens.json")
_STYLE_DICTIONARY_CONFIGS: tuple[str, ...] = (
    "style-dictionary.config.js",
    "style-dictionary.config.cjs",
    "style-dictionary.config.mjs",
    "style-dictionary.config.json",
)
_THEO_CONFIGS: tuple[str, ...] = ("theo.config.js",)


def _tokens_dir_has_content(repo: Path) -> bool:
    tokens = repo / "tokens"
    if not tokens.is_dir():
        return False
    for ext in ("*.json", "*.yaml", "*.yml"):
        if next(tokens.glob(ext), None) is not None:
            return True
        if next(tokens.rglob(ext), None) is not None:
            return True
    return False


@register
class DesignTokensPlatform:
    slug = "design_tokens"
    kind = PlatformKind.TOKENS_ONLY
    priority = 40

    def detect(self, repo: Path) -> bool:
        if any((repo / t).exists() for t in _ROOT_TOKEN_FILES):
            return True
        if any((repo / c).exists() for c in _STYLE_DICTIONARY_CONFIGS):
            return True
        if any((repo / c).exists() for c in _THEO_CONFIGS):
            return True
        return _tokens_dir_has_content(repo)

    @property
    def design_globs(self) -> tuple[str, ...]:
        return DEFAULT_COMMON_GLOBS + (
            "tokens.json",
            "design-tokens.json",
            "tokens/**/*.json",
            "tokens/**/*.yaml",
            "tokens/**/*.yml",
            "properties/**/*.json",
            "theo.config.js",
            "style-dictionary.config.*",
            "config.json",
        )

    @property
    def skip_dirs(self) -> tuple[str, ...]:
        return ("build", "dist")

    @property
    def prompt_hint(self) -> str:
        return (
            "Target: standalone design-tokens repository. The content is "
            "already structured — extract tokens verbatim, preserving the "
            "token taxonomy (color.primary.500 etc.) and any `$value` / "
            "`$type` metadata from the W3C Design Tokens Format."
        )
