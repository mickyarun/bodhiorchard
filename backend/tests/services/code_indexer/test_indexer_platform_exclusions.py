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

# SPDX-License-Identifier: MIT
# Copyright (C) 2026 Arun Rajkumar

"""Tests for platform-aware exclusions reaching ``index_repo``.

``FlutterPlatform.skip_dirs`` lists names (``test``, ``ios``, ``android``,
``generated``) that are ambiguous outside Flutter — Go/Rust/JS use
``test/`` as a real source root, native iOS repos use ``ios/`` for source.
That's why they live on the platform tuple instead of the cross-language
``_VENDORED_DIRS`` set in ``skip_lists.py``.

For those names to actually exclude files, ``index_repo`` must detect the
platform and pass ``skip_dirs`` through as ``extra_skip_dirs`` to
``filter_paths``. These tests verify that wiring end-to-end by exercising
the same composition the indexer performs, without dragging in graphify's
extract/build/cluster pipeline (which would require valid Dart sources).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.code_indexer import _collect_repo_files
from app.services.code_indexer.skip_lists import filter_paths
from app.services.platforms.registry import detect_platform


@pytest.fixture
def flutter_repo(tmp_path: Path) -> Path:
    """Synthetic Flutter repo with realistic noise + one real source file."""
    files = {
        # Marker: a pubspec with the ``flutter:`` key triggers detection.
        "pubspec.yaml": "name: demo\ndependencies:\n  flutter:\n    sdk: flutter\n",
        # Real Dart source — must be kept.
        "lib/main.dart": "void main() {}\n",
        "lib/widgets/button.dart": "class Button {}\n",
        # Test trees — must be dropped via platform ``skip_dirs``.
        "test/widget_test.dart": "// flutter_test\n",
        "test_driver/perf.dart": "// driver\n",
        "integration_test/login_test.dart": "// e2e\n",
        # Native shims — must be dropped via platform ``skip_dirs``.
        "android/app/build.gradle": "apply plugin: 'com.android.application'\n",
        "android/local.properties": "sdk.dir=/x\n",
        "android/app/google-services.json": '{"project_info":{}}\n',
        "ios/Runner/Info.plist": "<plist></plist>\n",
        "ios/Runner/GoogleService-Info.plist": "<plist></plist>\n",
        # Generated Dart artefacts — dropped by global file patterns.
        "lib/models/user.g.dart": "// freezed\n",
        "lib/state/auth.freezed.dart": "// freezed\n",
        # lib/generated/ subtree — dropped by Flutter's ``generated`` entry.
        "lib/generated/intl_en.dart": "// l10n\n",
    }
    for rel, body in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return tmp_path


def _filter_like_index_repo(repo: Path) -> tuple[list[Path], int]:
    """Replicate ``index_repo``'s detect-then-filter composition."""
    platform = detect_platform(repo)
    extra_skip_dirs: set[str] = set(platform.skip_dirs) if platform else set()
    raw_files = _collect_repo_files(repo)
    return filter_paths(raw_files, repo, extra_skip_dirs=extra_skip_dirs)


def test_flutter_platform_is_detected(flutter_repo: Path) -> None:
    """Detection must resolve to Flutter; otherwise no platform skips apply."""
    platform = detect_platform(flutter_repo)
    assert platform is not None
    assert platform.slug == "flutter"


def test_real_dart_source_is_kept(flutter_repo: Path) -> None:
    kept, _ = _filter_like_index_repo(flutter_repo)
    rels = {p.relative_to(flutter_repo).as_posix() for p in kept}
    assert "lib/main.dart" in rels
    assert "lib/widgets/button.dart" in rels


@pytest.mark.parametrize(
    "rel_path",
    [
        # Test trees (platform-scoped exclusion)
        "test/widget_test.dart",
        "test_driver/perf.dart",
        "integration_test/login_test.dart",
        # Native shims (platform-scoped exclusion)
        "android/app/build.gradle",
        "android/local.properties",
        "android/app/google-services.json",
        "ios/Runner/Info.plist",
        "ios/Runner/GoogleService-Info.plist",
        # Generated Dart (global file-pattern exclusion)
        "lib/models/user.g.dart",
        "lib/state/auth.freezed.dart",
        # lib/generated/ subtree (platform-scoped ``generated`` exclusion)
        "lib/generated/intl_en.dart",
    ],
)
def test_flutter_noise_is_dropped(flutter_repo: Path, rel_path: str) -> None:
    kept, _ = _filter_like_index_repo(flutter_repo)
    rels = {p.relative_to(flutter_repo).as_posix() for p in kept}
    assert rel_path not in rels, f"unexpectedly kept {rel_path}"


def test_dropped_count_is_nonzero(flutter_repo: Path) -> None:
    """Sanity: the filter actually fired on at least one of the noise files."""
    _, dropped = _filter_like_index_repo(flutter_repo)
    assert dropped > 0
