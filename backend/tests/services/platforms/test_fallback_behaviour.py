# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Fallback-path tests for the design system extractor.

These pin the critical invariant: **Vuetify CDN boilerplate must never
appear in the output for a non-web repo.** Previously a Flutter repo
without Claude CLI available would silently produce Vuetify HTML —
exactly the bug the reviewer flagged with a screenshot.
"""

from __future__ import annotations

from app.services.design_system_extractor import (
    _extraction_instructions,
    _fallback_minimal,
    _platform_aware_fallback,
)
from app.services.platforms import get_platform


def test_flutter_fallback_does_not_emit_vuetify_cdn(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A Flutter fallback must not contain Vuetify CDN links or <v-app>."""
    platform = get_platform("flutter")
    md, _ = _fallback_minimal(tmp_path, platform)
    lower = md.lower()
    assert "vuetify" not in lower
    assert "cdn.jsdelivr.net" not in lower
    assert "<v-app>" not in md
    assert "flutter" in lower  # platform name mentioned
    assert "ThemeData" in md or "Flutter" in md


def test_android_fallback_mentions_xml_resources() -> None:
    platform = get_platform("android_native")
    out = _platform_aware_fallback(platform, file_contents={}, reason=None)
    assert "vuetify" not in out.lower()
    assert "android" in out.lower()
    # The idiom hint should mention Android XML resources
    assert "XML" in out or "android_native" in out


def test_ios_fallback_mentions_asset_catalog_or_swift() -> None:
    platform = get_platform("ios_native")
    out = _platform_aware_fallback(platform, file_contents={}, reason=None)
    assert "vuetify" not in out.lower()
    assert "ios_native" in out or "iOS" in out


def test_web_fallback_preserves_vuetify_boilerplate(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Parity: web platform still gets the Vuetify CDN boilerplate."""
    platform = get_platform("web_js")
    md, _ = _fallback_minimal(tmp_path, platform)
    assert "vuetify" in md.lower()
    assert "cdn.jsdelivr.net" in md


def test_fallback_includes_discovered_files_when_present() -> None:
    platform = get_platform("flutter")
    out = _platform_aware_fallback(
        platform,
        file_contents={"pubspec.yaml": "name: demo\n", "lib/theme.dart": "class Theme {}\n"},
        reason="Claude Code CLI not available",
    )
    assert "pubspec.yaml" in out
    assert "lib/theme.dart" in out
    assert "Claude Code CLI not available" in out


def test_fallback_reports_status_without_reason() -> None:
    platform = get_platform("ios_native")
    out = _platform_aware_fallback(platform, file_contents={}, reason=None)
    # No "Reason:" section when reason is None
    assert "**Reason:**" not in out
    # But still emits the Status header
    assert "## Status" in out


def test_fallback_points_user_at_settings_ai_config() -> None:
    platform = get_platform("flutter")
    out = _platform_aware_fallback(platform, file_contents={}, reason=None)
    assert "AI Config" in out or "Claude Code CLI" in out


# ── LLM prompt instructions (platform-aware) ──────────────────────────────


def test_web_instructions_request_cdn_boilerplate() -> None:
    instructions = _extraction_instructions(get_platform("web_js"))
    # Wireframe generators downstream depend on CDN boilerplate for web repos.
    assert "CDN Boilerplate" in instructions
    assert "package.json" in instructions


def test_flutter_instructions_forbid_cdn_and_vuetify() -> None:
    """The 10-minute timeout on Flutter was caused by Claude trying to
    produce CDN / Vuetify / CSS-variable sections that don't apply. The
    new Flutter instructions must explicitly tell the LLM to skip those."""
    instructions = _extraction_instructions(get_platform("flutter"))
    assert "CDN" not in instructions or "do NOT emit CDN" in instructions
    assert "Vuetify" not in instructions or "Vuetify boilerplate" in instructions
    # And it should mention Flutter's native idiom
    assert "Flutter" in instructions or "TextStyle" in instructions


def test_non_web_instructions_have_fewer_sections() -> None:
    """Web asks for 6 sections; non-web asks for 3 focused ones. This is
    the structural difference that avoids the 10-minute timeout."""
    web = _extraction_instructions(get_platform("web_js"))
    assert "1. **Color Palette**" in web
    assert "6. **Pattern Library**" in web  # web still has 6 sections

    for slug in ("flutter", "android_native", "ios_native"):
        instr = _extraction_instructions(get_platform(slug))
        assert "1. **Color Palette**" in instr
        assert "2. **Typography**" in instr
        assert "3. **Platform Tokens**" in instr
        # No 4th/5th/6th section.
        assert "4. **" not in instr
        assert "5. **" not in instr
        assert "6. **" not in instr


def test_android_instructions_mention_text_appearance() -> None:
    assert "TextAppearance" in _extraction_instructions(get_platform("android_native"))


def test_ios_instructions_mention_native_idiom() -> None:
    instr = _extraction_instructions(get_platform("ios_native"))
    # iOS idiom: Font / SwiftUI
    assert "Font" in instr or "iOS" in instr
