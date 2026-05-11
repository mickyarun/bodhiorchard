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

"""Nuxt auto-import resolver for Pinia stores.

Nuxt 3 exposes every file under ``stores/**/*.{ts,js}`` as a callable
``useXxxStore`` symbol where ``Xxx`` is the filename with its first letter
upper-cased. Components and pages call those without a literal ``import``
line — the import-following pass in :mod:`endpoint_extractor` therefore
misses the API calls inside those store files.

This module builds a ``{useXxxStore: Path}`` map from the repo so the
expansion pass can pull store files into the frontier. Layer directories
(Nuxt's ``layers/<name>/stores``) merge into the same namespace and are
walked too — that is just any ``stores`` directory anywhere under the
repo root.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

_STORE_DIR_NAMES = ("stores", "store")
_STORE_EXTS = (".ts", ".js", ".mjs")
_USE_STORE_RE = re.compile(r"\buse([A-Z][A-Za-z0-9_]*?)Store\b")
_SKIP_DIRS = frozenset(
    {"node_modules", "dist", "build", "out", "coverage", "vendor", "__pycache__"}
)


def build_store_map(repo_root: Path) -> dict[str, Path]:
    """Return ``{useXxxStore: file_path}`` for every Pinia store in the repo.

    Walks every directory whose basename is ``stores`` / ``store`` (any
    nesting depth) and indexes its ``.ts`` / ``.js`` files. Hidden dirs
    and ``node_modules`` are skipped. First match wins so a root store
    shadows a layer-local file with the same name — matching Nuxt's
    layer-merge precedence.
    """
    out: dict[str, Path] = {}
    if not repo_root.is_dir():
        return out
    for store_dir in _iter_store_dirs(repo_root):
        for fp in store_dir.rglob("*"):
            if not fp.is_file() or fp.suffix not in _STORE_EXTS:
                continue
            symbol = _filename_to_use_symbol(fp.stem)
            if symbol and symbol not in out:
                out[symbol] = fp.resolve()
    return out


def find_store_references(text: str) -> set[str]:
    """Return ``{useXxxStore, ...}`` names referenced anywhere in ``text``."""
    return {f"use{m.group(1)}Store" for m in _USE_STORE_RE.finditer(text)}


def _iter_store_dirs(repo_root: Path) -> Iterator[Path]:
    """Yield every directory named ``stores`` / ``store`` under ``repo_root``.

    Skips hidden directories and standard build / vendor folders to
    avoid scanning cached, generated, or transpiled output.
    """
    for path in repo_root.rglob("*"):
        if not path.is_dir():
            continue
        try:
            rel_parts = path.relative_to(repo_root).parts
        except ValueError:
            continue
        if any(part.startswith(".") or part in _SKIP_DIRS for part in rel_parts):
            continue
        if path.name in _STORE_DIR_NAMES:
            yield path


def _filename_to_use_symbol(stem: str) -> str | None:
    """Convert ``auth`` → ``useAuthStore`` and ``googlePay`` → ``useGooglePayStore``.

    Returns ``None`` for empty stems or files starting with a non-letter
    (e.g. ``index``-only style stores are handled but ``.eslintrc``-style
    dotfiles never reach here because of the suffix filter upstream).
    """
    if not stem or not stem[0].isalpha():
        return None
    if stem == "index":
        return None
    return f"use{stem[0].upper()}{stem[1:]}Store"
