# SPDX-License-Identifier: MIT
# Copyright (C) 2026 Arun Rajkumar

"""Cross-language vendor / build-artefact skip list.

graphify's ``collect_files`` walks the entire repo and applies its own
small skip list (sensitive files like ``.env``, plus iOS asset bundles).
That misses the largest sources of noise for real repos: package-manager
caches (``node_modules``, ``Pods``, ``vendor``, …), build outputs
(``target``, ``dist``, ``build``, ``_build``, …), IDE metadata, and
language-specific cache directories.

Without filtering them out, a Node.js project's ``node_modules`` (often
40k+ files, 700MB) drowns the actual ``src`` tree, the call graph
becomes 95% library symbols, and Leiden produces giant ``kubernetes`` /
``v2010`` (Twilio) / ``es2024`` (TypeScript stdlib) clusters that
overshadow domain code.

This module owns the skip rules. Two layers:

1. **Directory-name skip set** — if any path component matches, the file
   is dropped. Covers ~99% of vendored content because every ecosystem
   uses a small number of well-known directory names.
2. **Filename-pattern skip set** — for individual files like
   ``*.min.js``, ``*.bundle.js``, ``*.lock``, ``*.snap`` that are
   generated regardless of where they live.

The directory list is drawn from these ecosystems:

  JS/TS/Node   — node_modules, bower_components, jspm_packages, .yarn,
                 .next, .nuxt, .turbo, .svelte-kit, .astro, .docusaurus,
                 .parcel-cache
  Python       — __pycache__, .venv, venv, env, .env, .tox,
                 .pytest_cache, .mypy_cache, .ruff_cache, htmlcov,
                 .ipynb_checkpoints, *.egg-info
  Go           — vendor (also Ruby/PHP/generic), bin
  Rust         — target (also JVM)
  JVM          — .gradle, .mvn, target, build, out
  Swift/iOS    — Pods, Carthage, DerivedData, .build
  .NET         — bin, obj, packages, .vs
  Ruby         — vendor, .bundle, pkg, tmp, log
  PHP          — vendor
  Elixir       — _build, deps, cover, .elixir_ls
  Dart/Flutter — .dart_tool, .pub-cache, .flutter-plugins
  C/C++/Bazel  — third_party, third-party, external, bazel-* (symlinks)
  Generic      — build, dist, out, coverage, .coverage, tmp, temp,
                 .idea, .vscode, .fleet, .vs, .cache, cdk.out,
                 .serverless, .terraform, _site, .jekyll-cache
  bodhi        — .bodhiorchard, .gitnexus

Override hooks: ``is_vendored`` accepts an optional ``extra_skip_dirs``
set so a per-repo config (or a unit test) can extend the list without
mutating module state.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

# ── Directory-name skip set ─────────────────────────────────────────
#
# Cross-language. If ANY component of a path (relative to the repo
# root) matches one of these names, the path is dropped. We do NOT skip
# the repo root itself even if its name happens to match — only
# directories *inside* the repo trigger the rule.

_VENDORED_DIRS: frozenset[str] = frozenset(
    {
        # ── JS / TS / Node ──────────────────────────────────────
        "node_modules",
        "bower_components",
        "jspm_packages",
        ".yarn",
        ".next",
        ".nuxt",
        ".turbo",
        ".cache",
        ".parcel-cache",
        ".svelte-kit",
        ".astro",
        ".docusaurus",
        ".vercel",
        ".netlify",
        # ── Python ──────────────────────────────────────────────
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        "venv",
        ".venv",
        "site-packages",
        "htmlcov",
        ".ipynb_checkpoints",
        ".eggs",
        # NB: ``env``/``.env`` as a directory name conflicts with
        # the common pattern of an ``env/`` config dir holding code.
        # We only skip ``.env`` to be conservative.
        ".env",
        # ── Go / Ruby / PHP / generic vendoring ─────────────────
        "vendor",
        # ── Rust / Java / .NET / generic build output ───────────
        "target",
        "build",
        "dist",
        "out",
        "bin",
        "obj",
        # ── JVM ─────────────────────────────────────────────────
        ".gradle",
        ".mvn",
        # ── Swift / iOS ─────────────────────────────────────────
        "Pods",
        "Carthage",
        "DerivedData",
        ".build",
        ".swiftpm",
        # ── .NET ────────────────────────────────────────────────
        "packages",
        ".vs",
        # ── Ruby ────────────────────────────────────────────────
        ".bundle",
        # NB: ``pkg/`` deliberately NOT skipped — Go projects use
        # ``pkg/<domain>/foo.go`` for first-class source code. Ruby's
        # ``bundle package`` writes vendored gems there too but is
        # rarely committed. Indexing a stray Ruby ``pkg/`` produces
        # a few junk clusters; skipping it would lose all Go user
        # code in monorepo / hex layouts.
        # NB: ``tmp/`` and ``log/`` are Rails defaults but also
        # legitimate names elsewhere — skip them to match the 99%
        # case (Rails apps).
        "tmp",
        "temp",
        "log",
        # ── Elixir ──────────────────────────────────────────────
        "_build",
        "deps",
        "cover",
        ".elixir_ls",
        # ── Dart / Flutter ──────────────────────────────────────
        ".dart_tool",
        ".pub-cache",
        # ── C / C++ / Bazel / monorepo ──────────────────────────
        "third_party",
        "third-party",
        "external",
        "cmake-build-debug",
        "cmake-build-release",
        # ── Generic test / coverage ─────────────────────────────
        "coverage",
        ".coverage",
        ".nyc_output",
        # ── IDE / editor metadata ───────────────────────────────
        ".idea",
        ".vscode",
        ".fleet",
        # ── VCS metadata ────────────────────────────────────────
        # .git is already not in the source tree by graphify defaults
        # but defensive on bare-repo / unusual layouts.
        ".git",
        ".svn",
        ".hg",
        # ── Infra-as-code generated ─────────────────────────────
        "cdk.out",
        ".serverless",
        ".terraform",
        # ── Static-site generated output ────────────────────────
        "_site",
        ".jekyll-cache",
        # ── bodhi internals + legacy gitnexus ───────────────────
        ".bodhiorchard",
        ".gitnexus",
    }
)


# ── Glob-style suffix patterns for individual files ────────────────
#
# Compiled once at import. Match against the file *basename*, not the
# full path, so we don't accidentally over-match by directory.

_VENDORED_FILE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\.min\.(js|css|mjs|cjs)$"),
    re.compile(r"\.bundle\.(js|mjs|cjs)$"),
    re.compile(r"\.chunk\.(js|mjs|cjs)$"),
    # Source maps
    re.compile(r"\.map$"),
    # Yarn Berry's PnP loader files at the repo root (auto-generated,
    # large, not source code we want to index).
    re.compile(r"^\.pnp\.(cjs|js|data\.json|loader\.mjs)$"),
    # Dependency manifests we don't want to parse as code
    re.compile(r"^package-lock\.json$"),
    re.compile(r"^yarn\.lock$"),
    re.compile(r"^pnpm-lock\.yaml$"),
    re.compile(r"^poetry\.lock$"),
    re.compile(r"^Pipfile\.lock$"),
    re.compile(r"^Cargo\.lock$"),
    re.compile(r"^Gemfile\.lock$"),
    re.compile(r"^composer\.lock$"),
    re.compile(r"^mix\.lock$"),
    re.compile(r"^Podfile\.lock$"),
    # Ruby built gems (replacement for the dropped ``pkg/`` dir-skip,
    # which conflicted with Go's ``pkg/<domain>/`` source-code layout).
    re.compile(r"\.gem$"),
    # Compiled artefacts
    re.compile(r"\.pyc$"),
    re.compile(r"\.pyo$"),
    re.compile(r"\.class$"),
    re.compile(r"\.o$"),
    re.compile(r"\.obj$"),
    re.compile(r"\.a$"),
    # Jest / snapshot output
    re.compile(r"\.snap$"),
)


# Bazel symlinks: ``bazel-bin``, ``bazel-out``, ``bazel-genfiles``,
# etc. — they're symlinks at the repo root pointing at the build
# sandbox. Detected by name prefix on the *first* path component.
_BAZEL_SYMLINK_PATTERN: re.Pattern[str] = re.compile(r"^bazel-")


# Suffix patterns: ``foo.egg-info`` is a directory, but its name is
# not a fixed string — match by suffix.
_VENDORED_DIR_SUFFIXES: tuple[str, ...] = (
    ".egg-info",
    ".egg",
    ".dist-info",
)


def is_vendored(
    path: str | Path,
    repo_root: str | Path,
    *,
    extra_skip_dirs: Iterable[str] = (),
) -> bool:
    """Return True iff ``path`` should be excluded from indexing.

    ``path`` and ``repo_root`` may be absolute or relative; the function
    works on the components *under* ``repo_root`` so the repo's own name
    cannot accidentally trigger the rule (e.g. a project literally named
    ``vendor`` is fine — we only skip ``./vendor/``).

    ``extra_skip_dirs`` lets callers extend the rule per-repo without
    monkey-patching the module-level set. Pass-through to a future
    per-org config knob.
    """
    p = Path(path)
    root = Path(repo_root).resolve()
    try:
        rel_parts = p.resolve().relative_to(root).parts
    except ValueError:
        # ``path`` is not under ``repo_root`` — out of scope, skip it
        # to be safe (treat as vendored).
        return True

    if not rel_parts:
        return False

    # First-component-only Bazel symlink check
    if _BAZEL_SYMLINK_PATTERN.match(rel_parts[0]):
        return True

    skip_set: set[str] = set(_VENDORED_DIRS) | set(extra_skip_dirs)
    for component in rel_parts[:-1]:  # directories above the file
        if component in skip_set:
            return True
        for suffix in _VENDORED_DIR_SUFFIXES:
            if component.endswith(suffix):
                return True

    basename = rel_parts[-1]
    return any(pattern.search(basename) for pattern in _VENDORED_FILE_PATTERNS)


def filter_paths(
    paths: Iterable[Path],
    repo_root: str | Path,
    *,
    extra_skip_dirs: Iterable[str] = (),
) -> tuple[list[Path], int]:
    """Filter ``paths`` against the skip rules.

    Returns ``(kept, dropped_count)`` so callers can log how aggressive
    the filter was on this repo.
    """
    extra = list(extra_skip_dirs)
    kept: list[Path] = []
    dropped = 0
    for p in paths:
        if is_vendored(p, repo_root, extra_skip_dirs=extra):
            dropped += 1
            continue
        kept.append(p)
    return kept, dropped


__all__ = [
    "filter_paths",
    "is_vendored",
]
