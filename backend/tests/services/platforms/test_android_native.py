# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Native Android detection tests."""

from __future__ import annotations

from pathlib import Path

from app.services.platforms import PlatformKind, detect_platform


def _build_android_tree(repo: Path, *, manifest: bool = True, gradle: bool = True) -> None:
    if manifest:
        (repo / "app" / "src" / "main").mkdir(parents=True, exist_ok=True)
        (repo / "app" / "src" / "main" / "AndroidManifest.xml").write_text(
            '<?xml version="1.0"?><manifest package="com.example.app"/>',
        )
    if gradle:
        (repo / "build.gradle.kts").write_text('plugins { id("com.android.application") }')


def test_detects_standard_android_app(tmp_path: Path) -> None:
    _build_android_tree(tmp_path)
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "android_native"
    assert platform.kind == PlatformKind.MOBILE_NATIVE


def test_requires_both_manifest_and_gradle(tmp_path: Path) -> None:
    _build_android_tree(tmp_path, manifest=True, gradle=False)
    # Manifest alone is not enough — may be a non-Android XML project.
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "backend"


def test_does_not_claim_pure_kotlin_jvm_project(tmp_path: Path) -> None:
    _build_android_tree(tmp_path, manifest=False, gradle=True)
    # Gradle alone is a JVM / KMP project, not Android.
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "backend"


def test_globs_include_compose_and_xml(tmp_path: Path) -> None:
    _build_android_tree(tmp_path)
    platform = detect_platform(tmp_path)
    assert platform is not None
    globs = platform.design_globs
    assert "**/res/values/colors.xml" in globs
    assert "**/ui/theme/Theme.kt" in globs
    assert "**/res/values-night/colors.xml" in globs
