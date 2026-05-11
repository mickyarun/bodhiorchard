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

"""Tests for ``app.services.code_indexer.skip_lists``.

Per-language coverage of the vendor / build-artefact filter so a
regression in any one ecosystem fails loudly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.code_indexer.skip_lists import filter_paths, is_vendored


def _run(rel_path: str, *, repo_root: str = "/repo") -> bool:
    """Helper: ask whether the given repo-relative path is vendored.

    Uses string paths only — the implementation must accept those.
    """
    return is_vendored(f"{repo_root}/{rel_path}", repo_root)


# ── Real source code: must be KEPT ─────────────────────────────────


@pytest.mark.parametrize(
    "rel_path",
    [
        "src/services/auth/AuthService.ts",
        "app/models/user.py",
        "lib/payments.rb",
        "internal/handlers/checkout.go",
        "cmd/server/main.go",
        "src/main/java/com/co/Service.java",
        "Sources/MyApp/Auth.swift",
        "lib/atoa/payments.ex",
        "app/Http/Controllers/UserController.php",
        "frontend/components/Button.vue",
        "src/index.tsx",
        "lib/index.dart",
        "src/lib.rs",
    ],
)
def test_real_source_code_is_kept(rel_path: str) -> None:
    assert not _run(rel_path), f"unexpectedly skipped {rel_path}"


# ── JavaScript / TypeScript / Node ─────────────────────────────────


@pytest.mark.parametrize(
    "rel_path",
    [
        "node_modules/lodash/index.js",
        "node_modules/@kubernetes/client-node/dist/api.d.ts",
        "bower_components/jquery/jquery.min.js",
        "jspm_packages/foo.js",
        ".yarn/cache/lodash.zip",
        ".pnp.cjs",
        ".next/server/pages/index.js",
        ".nuxt/dist/server/index.js",
        ".turbo/cache/foo.txt",
        ".cache/something",
        ".svelte-kit/output/server.js",
        ".astro/types.d.ts",
        ".docusaurus/registry.json",
        ".vercel/cache/.x",
        ".netlify/functions/handler.js",
        ".parcel-cache/foo.js",
    ],
)
def test_javascript_vendored_is_dropped(rel_path: str) -> None:
    assert _run(rel_path), f"failed to skip {rel_path}"


# ── Python ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "rel_path",
    [
        "src/__pycache__/foo.cpython-312.pyc",
        ".pytest_cache/v/cache/lastfailed",
        ".mypy_cache/3.12/x/foo.json",
        ".ruff_cache/foo.json",
        ".tox/py312/lib/site.py",
        ".venv/lib/python3.12/site-packages/foo.py",
        "venv/bin/activate",
        "site-packages/numpy/__init__.py",
        "htmlcov/index.html",
        ".ipynb_checkpoints/Untitled-checkpoint.ipynb",
        ".eggs/some-1.0.egg/something.py",
        "mypkg.egg-info/PKG-INFO",
        "wheelhouse-thing.dist-info/RECORD",
    ],
)
def test_python_vendored_is_dropped(rel_path: str) -> None:
    assert _run(rel_path), f"failed to skip {rel_path}"


def test_python_egg_info_directory_with_files_under_it() -> None:
    """Ensure suffix-matched directories drop their members too."""
    assert _run("dist/mypkg-0.1.dist-info/METADATA")
    assert _run("backend/mypkg.egg-info/PKG-INFO")


# ── Go / Rust / JVM build output ───────────────────────────────────


@pytest.mark.parametrize(
    "rel_path",
    [
        # Go vendoring
        "vendor/github.com/foo/bar/main.go",
        # Rust
        "target/debug/foo",
        "target/release/build/abc/out/file.rs",
        # Maven / Gradle / generic build
        "target/classes/com/co/Foo.class",
        "build/classes/main/Foo.class",
        ".gradle/caches/modules-2/files-2.1/x.jar",
        ".mvn/wrapper/maven-wrapper.properties",
    ],
)
def test_go_rust_jvm_vendored_is_dropped(rel_path: str) -> None:
    assert _run(rel_path), f"failed to skip {rel_path}"


# ── Swift / iOS ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "rel_path",
    [
        "Pods/Alamofire/Source/Foo.swift",
        "Carthage/Build/iOS/Foo.framework/Foo",
        "DerivedData/MyApp/Build/Products/index.json",
        ".build/debug/MyApp",
        ".swiftpm/configuration/.x",
    ],
)
def test_swift_vendored_is_dropped(rel_path: str) -> None:
    assert _run(rel_path), f"failed to skip {rel_path}"


# ── .NET ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "rel_path",
    [
        "MyApp/bin/Debug/net8.0/MyApp.dll",
        "MyApp/obj/Debug/net8.0/Microsoft.NET.targets",
        "packages/Newtonsoft.Json.13.0.3/lib/net6.0/foo.dll",
        ".vs/MyApp/v17/.suo",
    ],
)
def test_dotnet_vendored_is_dropped(rel_path: str) -> None:
    assert _run(rel_path), f"failed to skip {rel_path}"


# ── Ruby / PHP ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "rel_path",
    [
        # Ruby Bundler
        "vendor/bundle/ruby/3.2.0/gems/foo-1.0.0/lib/foo.rb",
        ".bundle/config",
        "pkg/myapp-0.1.0.gem",
        "tmp/cache/something",
        "log/development.log",
        # PHP composer
        "vendor/symfony/console/Application.php",
    ],
)
def test_ruby_php_vendored_is_dropped(rel_path: str) -> None:
    assert _run(rel_path), f"failed to skip {rel_path}"


# ── Elixir / Erlang ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "rel_path",
    [
        "_build/dev/lib/myapp/ebin/Elixir.MyApp.beam",
        "deps/phoenix/lib/phoenix.ex",
        "cover/cover.html",
        ".elixir_ls/build.log",
    ],
)
def test_elixir_vendored_is_dropped(rel_path: str) -> None:
    assert _run(rel_path), f"failed to skip {rel_path}"


# ── Dart / Flutter ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "rel_path",
    [
        ".dart_tool/build/x.json",
        ".pub-cache/hosted/pub.dev/foo-1.0.0/lib/foo.dart",
        "build/app/intermediates/x.json",
    ],
)
def test_dart_vendored_is_dropped(rel_path: str) -> None:
    assert _run(rel_path), f"failed to skip {rel_path}"


# ── C / C++ / Bazel ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "rel_path",
    [
        "third_party/zlib/zlib.h",
        "third-party/zlib/zlib.h",
        "external/grpc/server.cc",
        "cmake-build-debug/CMakeFiles/x.cmake",
        "cmake-build-release/x.so",
        # Bazel symlinks at the repo root
        "bazel-bin/myapp/server",
        "bazel-out/x86-fastbuild/x.h",
        "bazel-genfiles/proto/x.pb.h",
    ],
)
def test_c_cpp_bazel_vendored_is_dropped(rel_path: str) -> None:
    assert _run(rel_path), f"failed to skip {rel_path}"


# ── Generic build / coverage / IDE / VCS ────────────────────────────


@pytest.mark.parametrize(
    "rel_path",
    [
        "build/output.js",
        "dist/main.js",
        "out/server.js",
        "coverage/lcov.info",
        ".coverage/data",
        ".nyc_output/123.json",
        ".idea/workspace.xml",
        ".vscode/settings.json",
        ".fleet/run.json",
        ".git/objects/pack/foo",
        ".svn/entries",
        ".hg/cache/x",
        "cdk.out/cdk.json",
        ".serverless/cloudformation-template.json",
        ".terraform/providers/x/y/0.1.0/lock.json",
        "_site/index.html",
        ".jekyll-cache/x",
    ],
)
def test_generic_vendored_is_dropped(rel_path: str) -> None:
    assert _run(rel_path), f"failed to skip {rel_path}"


# ── bodhi internals + legacy gitnexus ───────────────────────────────


@pytest.mark.parametrize(
    "rel_path",
    [
        ".bodhiorchard/scan-wt/main/src/foo.ts",
        ".gitnexus/meta.json",
    ],
)
def test_bodhi_internals_dropped(rel_path: str) -> None:
    assert _run(rel_path), f"failed to skip {rel_path}"


# ── File-pattern rules (regardless of directory) ───────────────────


@pytest.mark.parametrize(
    "rel_path",
    [
        "src/dist/jquery.min.js",
        "src/lib/lodash.bundle.js",
        "src/foo.chunk.js",
        "src/foo.js.map",
        "src/foo.css.map",
        # lock files
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "Pipfile.lock",
        "Cargo.lock",
        "Gemfile.lock",
        "composer.lock",
        "mix.lock",
        "Podfile.lock",
        # compiled artefacts
        "src/foo.pyc",
        "src/Foo.class",
        "src/foo.o",
        "src/Foo.obj",
        "src/lib.a",
        "tests/__snapshots__/Component.test.tsx.snap",
    ],
)
def test_file_patterns(rel_path: str) -> None:
    assert _run(rel_path), f"failed to skip {rel_path}"


# ── Edge cases ──────────────────────────────────────────────────────


def test_repo_named_vendor_is_not_self_skipped() -> None:
    """A repo literally named 'vendor' should index its own src cleanly."""
    # Repo root is /vendor; file is /vendor/src/foo.go. The 'vendor' in
    # the root name must NOT trigger the rule.
    assert not is_vendored("/vendor/src/foo.go", "/vendor")


def test_path_outside_repo_root_is_treated_as_vendored() -> None:
    """Defensive: a path not under repo_root should be treated as vendored."""
    assert is_vendored("/elsewhere/src/foo.py", "/repo")


def test_extra_skip_dirs_extends_default() -> None:
    """Per-call skip-list extension takes effect."""
    rel = "/repo/legacy/old.js"
    assert not is_vendored(rel, "/repo")  # not in default set
    assert is_vendored(rel, "/repo", extra_skip_dirs={"legacy"})


def test_filter_paths_returns_kept_and_dropped_count() -> None:
    paths = [
        Path("/repo/src/foo.ts"),
        Path("/repo/node_modules/x.js"),
        Path("/repo/src/bar.ts"),
        Path("/repo/dist/out.js"),
        Path("/repo/Pods/Foo/Bar.swift"),
    ]
    kept, dropped = filter_paths(paths, "/repo")
    assert len(kept) == 2
    assert dropped == 3
    assert all("src/" in str(p) for p in kept)


def test_top_level_source_files_are_kept() -> None:
    """README.md, package.json, etc. at the root must NOT match a directory rule."""
    assert not _run("README.md")
    assert not _run("Cargo.toml")
    assert not _run("pyproject.toml")
    # But package-lock.json IS skipped by file-pattern rule:
    assert _run("package-lock.json")
