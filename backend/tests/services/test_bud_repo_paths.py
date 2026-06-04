# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""Unit tests for ``bud_repo_paths.confirmed_repo_paths``.

Pins the metadata-shape contract: missing key, malformed entries, and
the fallback merge all behave consistently so the multi-repo refresh
loop never spawns ``git`` against an empty or duplicated path list.
"""

from unittest.mock import MagicMock

from app.services.bud_repo_paths import confirmed_repo_paths


def _bud_with_meta(meta: dict[str, object] | None) -> MagicMock:
    bud = MagicMock()
    bud.metadata_ = meta
    return bud


def test_extracts_paths_in_order() -> None:
    bud = _bud_with_meta(
        {
            "confirmed_repos": [
                {"repo_name": "A", "repo_path": "/clone/a"},
                {"repo_name": "B", "repo_path": "/clone/b"},
            ]
        }
    )
    assert confirmed_repo_paths(bud) == ["/clone/a", "/clone/b"]


def test_returns_empty_when_metadata_missing() -> None:
    assert confirmed_repo_paths(_bud_with_meta(None)) == []
    assert confirmed_repo_paths(_bud_with_meta({})) == []
    assert confirmed_repo_paths(_bud_with_meta({"confirmed_repos": None})) == []


def test_skips_malformed_entries() -> None:
    bud = _bud_with_meta(
        {
            "confirmed_repos": [
                {"repo_path": "/clone/a"},
                "not-a-dict",
                {"repo_path": ""},
                {"repo_name": "no-path-key"},
                {"repo_path": 123},
                {"repo_path": "/clone/b"},
            ]
        }
    )
    assert confirmed_repo_paths(bud) == ["/clone/a", "/clone/b"]


def test_fallback_appended_when_absent() -> None:
    bud = _bud_with_meta({"confirmed_repos": [{"repo_path": "/clone/a"}]})
    assert confirmed_repo_paths(bud, fallback="/clone/scratch") == [
        "/clone/a",
        "/clone/scratch",
    ]


def test_fallback_not_duplicated_when_already_present() -> None:
    bud = _bud_with_meta(
        {
            "confirmed_repos": [
                {"repo_path": "/clone/a"},
                {"repo_path": "/clone/b"},
            ]
        }
    )
    assert confirmed_repo_paths(bud, fallback="/clone/a") == ["/clone/a", "/clone/b"]


def test_dedupes_repeated_paths() -> None:
    bud = _bud_with_meta(
        {
            "confirmed_repos": [
                {"repo_path": "/clone/a"},
                {"repo_path": "/clone/a"},
                {"repo_path": "/clone/b"},
            ]
        }
    )
    assert confirmed_repo_paths(bud) == ["/clone/a", "/clone/b"]


def test_no_fallback_when_none() -> None:
    bud = _bud_with_meta({"confirmed_repos": [{"repo_path": "/clone/a"}]})
    assert confirmed_repo_paths(bud, fallback=None) == ["/clone/a"]
