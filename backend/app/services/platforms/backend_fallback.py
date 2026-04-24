# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Catch-all platform — matches any repo that no other platform claims.

Kept at priority 0 so every specific platform is evaluated first. ``kind`` is
``BACKEND`` so the design-system extractor's UI gate rejects these repos.
"""

from __future__ import annotations

from pathlib import Path

from app.services.platforms.base import PlatformKind
from app.services.platforms.registry import register


@register
class BackendFallbackPlatform:
    slug = "backend"
    kind = PlatformKind.BACKEND
    priority = 0

    def detect(self, repo: Path) -> bool:  # noqa: ARG002 — signature required by Protocol
        return True

    @property
    def design_globs(self) -> tuple[str, ...]:
        return ()

    @property
    def skip_dirs(self) -> tuple[str, ...]:
        return ()

    @property
    def prompt_hint(self) -> str:
        return ""
