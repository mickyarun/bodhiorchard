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

"""Detection tests for .NET family + Qt + Compose Desktop + SwiftUI macOS."""

from __future__ import annotations

from pathlib import Path

from app.services.platforms import PlatformKind, detect_platform


def _csproj(repo: Path, name: str, body: str) -> None:
    (repo / name).write_text(body)


# ── Blazor ────────────────────────────────────────────────────────────────


def test_blazor_requires_both_razor_and_csproj_reference(tmp_path: Path) -> None:
    _csproj(
        tmp_path,
        "app.csproj",
        '<Project Sdk="Microsoft.NET.Sdk.Web">'
        '<ItemGroup><PackageReference Include="Microsoft.AspNetCore.Components.Web"/></ItemGroup>'
        "</Project>",
    )
    (tmp_path / "App.razor").write_text('<Router AppAssembly="..."/>')
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "blazor"
    assert platform.kind == PlatformKind.DESKTOP


def test_blazor_without_razor_files_rejects(tmp_path: Path) -> None:
    _csproj(
        tmp_path,
        "app.csproj",
        "<Project><ItemGroup>"
        '<PackageReference Include="Microsoft.AspNetCore.Components.Web"/>'
        "</ItemGroup></Project>",
    )
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "backend"


# ── MAUI ──────────────────────────────────────────────────────────────────


def test_dotnet_maui(tmp_path: Path) -> None:
    _csproj(
        tmp_path,
        "App.csproj",
        "<Project><PropertyGroup><UseMaui>true</UseMaui></PropertyGroup></Project>",
    )
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "dotnet_maui"


# ── WPF ───────────────────────────────────────────────────────────────────


def test_wpf(tmp_path: Path) -> None:
    _csproj(
        tmp_path,
        "App.csproj",
        "<Project><PropertyGroup><UseWPF>true</UseWPF></PropertyGroup></Project>",
    )
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "wpf"


# ── Avalonia ──────────────────────────────────────────────────────────────


def test_avalonia(tmp_path: Path) -> None:
    _csproj(
        tmp_path,
        "App.csproj",
        "<Project><ItemGroup>"
        '<PackageReference Include="Avalonia" Version="11.0.0"/>'
        "</ItemGroup></Project>",
    )
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "avalonia"


# ── Qt ────────────────────────────────────────────────────────────────────


def test_qt_pro_file(tmp_path: Path) -> None:
    (tmp_path / "app.pro").write_text("QT += core gui widgets\n")
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "qt"


def test_qt_cmake_find_package(tmp_path: Path) -> None:
    (tmp_path / "CMakeLists.txt").write_text("find_package(Qt6 COMPONENTS Widgets REQUIRED)\n")
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "qt"


def test_qt_qml_file(tmp_path: Path) -> None:
    (tmp_path / "ui").mkdir()
    (tmp_path / "ui" / "Main.qml").write_text("import QtQuick\nItem {}\n")
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "qt"


# ── Compose Desktop ───────────────────────────────────────────────────────


def test_compose_desktop_via_gradle_kts(tmp_path: Path) -> None:
    (tmp_path / "build.gradle.kts").write_text(
        'plugins { id("org.jetbrains.compose") version "1.5.0" }\n',
    )
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "compose_desktop"


# ── SwiftUI macOS ─────────────────────────────────────────────────────────


def test_swiftui_macos_targets_only_macos(tmp_path: Path) -> None:
    proj = tmp_path / "App.xcodeproj"
    proj.mkdir()
    (proj / "project.pbxproj").write_text("SDKROOT = macosx;\n")
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "swiftui_macos"


def test_swiftui_macos_loses_to_ios_when_iphoneos_present(tmp_path: Path) -> None:
    proj = tmp_path / "App.xcodeproj"
    proj.mkdir()
    (proj / "project.pbxproj").write_text("SDKROOT = iphoneos;\n")
    platform = detect_platform(tmp_path)
    assert platform is not None
    assert platform.slug == "ios_native"
