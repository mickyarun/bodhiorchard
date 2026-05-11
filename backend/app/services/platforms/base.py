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

"""Platform detection contract.

A Platform classifies a repository by its frontend / UI toolchain so downstream
services (design-system extraction, skill analysis, MCP context) can adapt to
the idioms of that toolchain. Every platform owns its markers, glob patterns,
skip directories, and LLM prompt hint — there is no central table.

New platforms plug in by subclassing :class:`Platform` and decorating with
``@register`` from :mod:`app.services.platforms.registry`. See
``platforms/README.md`` for the full recipe.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable

# Globs every UI-bearing platform benefits from. Platforms opt in by including
# them in their ``design_globs``; there is no hidden union.
DEFAULT_COMMON_GLOBS: tuple[str, ...] = (
    "README.md",
    "docs/design/**/*.md",
)

# Directories every platform should skip. Platform-specific skip dirs are
# unioned on top of this by the extractor.
DEFAULT_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        "coverage",
        ".next",
        ".nuxt",
    }
)


class PlatformKind(StrEnum):
    """Coarse-grained platform categories used for gating and presentation."""

    WEB = "web"
    MOBILE_NATIVE = "mobile_native"
    MOBILE_CROSS = "mobile_cross"
    DESKTOP = "desktop"
    STATIC_SITE = "static_site"
    TOKENS_ONLY = "tokens_only"
    BACKEND = "backend"


UI_KINDS: frozenset[PlatformKind] = frozenset(
    {
        PlatformKind.WEB,
        PlatformKind.MOBILE_NATIVE,
        PlatformKind.MOBILE_CROSS,
        PlatformKind.DESKTOP,
        PlatformKind.STATIC_SITE,
        PlatformKind.TOKENS_ONLY,
    }
)


@runtime_checkable
class Platform(Protocol):
    """A UI / frontend toolchain the scanner recognizes.

    Implementations are stateless: a single instance is registered at import
    time and reused for every detection call.
    """

    slug: str
    kind: PlatformKind
    priority: int

    def detect(self, repo: Path) -> bool:
        """Return True when the repo is built with this platform."""
        ...

    @property
    def design_globs(self) -> tuple[str, ...]:
        """Glob patterns (repo-relative) pointing at design-token sources."""
        ...

    @property
    def skip_dirs(self) -> tuple[str, ...]:
        """Directory names to skip during discovery (unioned with defaults)."""
        ...

    @property
    def prompt_hint(self) -> str:
        """Platform-specific instruction prepended to the LLM extraction prompt."""
        ...
