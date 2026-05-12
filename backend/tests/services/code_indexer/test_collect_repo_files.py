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

"""Tests for the ``_collect_repo_files`` graphify-augmentation wrapper.

Graphify's ``collect_files`` omits ten extensions that its own dispatch
table can extract (.vue, .svelte, .jsx, .mjs, .dart, .ex, .exs, .jl, .v,
.sv). Without the wrapper, Vue / Svelte / Flutter / React-JSX / Elixir /
Julia / Verilog repos produce zero clusters even though graphify can
parse them. These tests fail loudly if any of those suffixes regress.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.code_indexer import _EXTRA_EXTENSIONS, _collect_repo_files


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """A small synthetic repo with one file per ecosystem we care about."""
    files = [
        # graphify already collects these — sanity baseline
        "src/lib.ts",
        "src/main.py",
        "src/app.go",
        # extensions the wrapper has to add
        "src/components/SplitBill.vue",
        "src/routes/+page.svelte",
        "src/legacy/Modal.jsx",
        "src/esm/index.mjs",
        "lib/main.dart",
        "lib/myapp/payments.ex",
        "test/payments_test.exs",
        "src/Project.jl",
        "rtl/cpu.v",
        "rtl/cpu_tb.sv",
    ]
    for rel in files:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("// stub\n", encoding="utf-8")
    return tmp_path


def test_extra_extensions_are_collected(fake_repo: Path) -> None:
    """Every suffix in ``_EXTRA_EXTENSIONS`` must show up in the result."""
    collected = {p.suffix for p in _collect_repo_files(fake_repo)}
    missing = _EXTRA_EXTENSIONS - collected
    assert not missing, f"wrapper failed to collect: {sorted(missing)}"


def test_baseline_extensions_still_collected(fake_repo: Path) -> None:
    """Wrapping graphify must not drop suffixes graphify already handles."""
    collected = {p.suffix for p in _collect_repo_files(fake_repo)}
    for ext in (".ts", ".py", ".go"):
        assert ext in collected, f"baseline graphify suffix {ext} missing"


def test_wrapper_skips_dotdirs(tmp_path: Path) -> None:
    """``.dart_tool/foo.dart`` and friends must not be collected.

    Graphify's own walker skips any path with a ``.``-prefixed component;
    the wrapper has to mirror that so vendored Dart / Elixir / Vue caches
    don't sneak in before ``filter_paths`` runs.
    """
    (tmp_path / ".dart_tool").mkdir()
    (tmp_path / ".dart_tool" / "vendor.dart").write_text("// vendored\n")
    (tmp_path / "lib").mkdir()
    real = tmp_path / "lib" / "main.dart"
    real.write_text("// real\n")
    paths = _collect_repo_files(tmp_path)
    assert real in paths
    assert not any(".dart_tool" in p.parts for p in paths)


def test_wrapper_dedupes_against_graphify_output(tmp_path: Path) -> None:
    """A ``.ts`` file must not appear twice — it's in graphify's set already."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.ts").write_text("export {}\n")
    (tmp_path / "src" / "App.vue").write_text("<script setup></script>\n")
    paths = _collect_repo_files(tmp_path)
    assert len(paths) == len(set(paths)), "duplicate paths in wrapper output"
