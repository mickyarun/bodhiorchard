# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Registry mechanics: ordering, lookup, empty-repo fallback."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.platforms import (
    PlatformKind,
    all_platforms,
    detect_platform,
    get_platform,
)


def test_all_platforms_sorted_by_priority_desc() -> None:
    platforms = all_platforms()
    priorities = [p.priority for p in platforms]
    assert priorities == sorted(priorities, reverse=True)


def test_get_platform_resolves_known_slug() -> None:
    platform = get_platform("web_js")
    assert platform.slug == "web_js"
    assert platform.kind == PlatformKind.WEB


def test_get_platform_raises_on_unknown_slug() -> None:
    with pytest.raises(KeyError):
        get_platform("totally-not-a-platform")


def test_backend_fallback_matches_empty_repo(tmp_path: Path) -> None:
    # Unknown/empty directory falls through to the backend fallback.
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "backend"
    assert platform.kind == PlatformKind.BACKEND


def test_backend_fallback_has_empty_design_globs() -> None:
    platform = get_platform("backend")
    assert platform.design_globs == ()
    assert platform.prompt_hint == ""


def test_every_registered_platform_has_unique_slug() -> None:
    slugs = [p.slug for p in all_platforms()]
    assert len(slugs) == len(set(slugs)), f"Duplicate slugs: {slugs}"


def test_tiebreak_is_slug_alphabetical_not_import_order() -> None:
    # Platforms at equal priority MUST appear in slug order, not in
    # whatever order ``__init__.py`` happened to import them. Guards
    # against a copy-paste in __init__.py silently reshuffling detection
    # for equal-priority platforms (e.g. the 80-bucket mobile native trio).
    same_priority: dict[int, list[str]] = {}
    for p in all_platforms():
        same_priority.setdefault(p.priority, []).append(p.slug)
    for priority, slugs in same_priority.items():
        assert slugs == sorted(slugs), f"Priority {priority} platforms not in slug order: {slugs}"
