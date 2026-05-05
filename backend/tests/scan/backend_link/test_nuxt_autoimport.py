# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Unit tests for ``backend_link.nuxt_autoimport``.

The Nuxt auto-import resolver maps filename-based store identifiers
(``stores/auth.ts`` → ``useAuthStore``) so the BFS expansion can reach
auto-imported Pinia stores even though no literal ``import`` statement
points at them.
"""

from __future__ import annotations

from pathlib import Path

from app.services.scan.backend_link.nuxt_autoimport import (
    build_store_map,
    find_store_references,
)


def _write(p: Path, contents: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(contents)


def test_simple_store_filename(tmp_path: Path) -> None:
    """``stores/auth.ts`` exposes ``useAuthStore``."""
    _write(tmp_path / "stores" / "auth.ts", "export const useAuthStore = defineStore(...)")
    store_map = build_store_map(tmp_path)
    assert "useAuthStore" in store_map
    assert store_map["useAuthStore"].name == "auth.ts"


def test_camel_case_filename_preserved(tmp_path: Path) -> None:
    """``googlePlatformReviews.ts`` → ``useGooglePlatformReviewsStore``."""
    _write(tmp_path / "stores" / "googlePlatformReviews.ts", "// store")
    store_map = build_store_map(tmp_path)
    assert "useGooglePlatformReviewsStore" in store_map


def test_layer_stores_walked(tmp_path: Path) -> None:
    """Nuxt layer dirs (``layers/foo/stores/``) merge into the namespace."""
    _write(tmp_path / "layers" / "feature-x" / "stores" / "x.ts", "// layer store")
    store_map = build_store_map(tmp_path)
    assert "useXStore" in store_map


def test_index_filename_skipped(tmp_path: Path) -> None:
    """``stores/index.ts`` doesn't make ``useIndexStore`` (it's the directory entry)."""
    _write(tmp_path / "stores" / "index.ts", "// barrel")
    store_map = build_store_map(tmp_path)
    assert "useIndexStore" not in store_map


def test_node_modules_skipped(tmp_path: Path) -> None:
    """``node_modules/.../stores/...`` is ignored."""
    _write(tmp_path / "node_modules" / "pkg" / "stores" / "leak.ts", "// noise")
    _write(tmp_path / "stores" / "real.ts", "// real")
    store_map = build_store_map(tmp_path)
    assert "useRealStore" in store_map
    assert "useLeakStore" not in store_map


def test_find_store_references_in_text() -> None:
    """``useAuthStore()`` and ``useFooStore`` references are detected."""
    text = """
import { defineComponent } from 'vue';
const auth = useAuthStore();
const foo = useFooStore;
const noise = userStore;  // does not match (lacks 'use' prefix)
"""
    refs = find_store_references(text)
    assert refs == {"useAuthStore", "useFooStore"}
