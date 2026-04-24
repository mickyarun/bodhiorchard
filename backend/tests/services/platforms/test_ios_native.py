# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Native iOS detection tests."""

from __future__ import annotations

from pathlib import Path

from app.services.platforms import PlatformKind, detect_platform


def test_detects_xcodeproj_at_root(tmp_path: Path) -> None:
    (tmp_path / "MyApp.xcodeproj").mkdir()
    (tmp_path / "MyApp.xcodeproj" / "project.pbxproj").write_text("// ...")
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "ios_native"
    assert platform.kind == PlatformKind.MOBILE_NATIVE


def test_detects_xcodeproj_under_ios_folder(tmp_path: Path) -> None:
    ios_dir = tmp_path / "ios" / "MyApp.xcodeproj"
    ios_dir.mkdir(parents=True)
    (ios_dir / "project.pbxproj").write_text("// ...")
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "ios_native"


def test_detects_podfile(tmp_path: Path) -> None:
    (tmp_path / "Podfile").write_text("platform :ios, '15.0'\n")
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "ios_native"


def test_swift_package_with_swiftui_import(tmp_path: Path) -> None:
    (tmp_path / "Package.swift").write_text("// swift-tools-version:5.9\n")
    (tmp_path / "Sources").mkdir()
    (tmp_path / "Sources" / "App.swift").write_text("import SwiftUI\nstruct App {}\n")
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "ios_native"


def test_swift_package_without_ui_imports_does_not_match(tmp_path: Path) -> None:
    (tmp_path / "Package.swift").write_text("// swift-tools-version:5.9\n")
    (tmp_path / "Sources").mkdir()
    (tmp_path / "Sources" / "Lib.swift").write_text("import Foundation\n")
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "backend"


def test_globs_include_asset_catalog_and_theme_swift(tmp_path: Path) -> None:
    (tmp_path / "MyApp.xcodeproj").mkdir()
    (tmp_path / "MyApp.xcodeproj" / "project.pbxproj").write_text("")
    platform = detect_platform(tmp_path)
    assert platform is not None
    globs = platform.design_globs
    assert any("Assets.xcassets" in g for g in globs)
    assert "**/*Theme*.swift" in globs
