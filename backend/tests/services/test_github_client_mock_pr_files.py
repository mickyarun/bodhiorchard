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

"""``BODHI_MOCK_PR_FILES_PATH`` short-circuit on ``list_pr_files``.

The smoke harness for the PR-merge narrow-synthesis path needs the
backend to behave as if a synthetic PR touched a specific file set
without making a real GitHub API call. Verify that the env-gated
short-circuit:

* returns the mocked file list when the env var points at a JSON file
  that contains a matching ``owner_repo:pr_number`` key,
* falls through (returns ``None`` from the helper) when the env var is
  unset OR the file/key isn't present, so production traffic is
  untouched whenever the var isn't set.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.github_client import GitHubClient, _read_mock_pr_files


def _write_mock_file(tmp_path: Path, payload: dict[str, list[str]]) -> Path:
    """Drop a JSON fixture matching the helper's expected shape."""
    p = tmp_path / "pr_files.json"
    p.write_text(json.dumps(payload))
    return p


def test_read_mock_returns_none_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BODHI_MOCK_PR_FILES_PATH", raising=False)
    assert _read_mock_pr_files("owner/repo", 7) is None


def test_read_mock_returns_files_on_key_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _write_mock_file(
        tmp_path,
        {"owner/repo:7": ["src/a.ts", "src/b.py"]},
    )
    monkeypatch.setenv("BODHI_MOCK_PR_FILES_PATH", str(fixture))
    assert _read_mock_pr_files("owner/repo", 7) == ["src/a.ts", "src/b.py"]


def test_read_mock_returns_none_when_key_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unrelated PRs in the same test run must NOT be short-circuited."""
    fixture = _write_mock_file(tmp_path, {"owner/repo:7": ["x.ts"]})
    monkeypatch.setenv("BODHI_MOCK_PR_FILES_PATH", str(fixture))
    assert _read_mock_pr_files("owner/other-repo", 99) is None


def test_read_mock_returns_none_when_file_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BODHI_MOCK_PR_FILES_PATH", str(tmp_path / "does-not-exist.json"))
    assert _read_mock_pr_files("owner/repo", 7) is None


def test_read_mock_returns_none_when_file_invalid_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("not json {")
    monkeypatch.setenv("BODHI_MOCK_PR_FILES_PATH", str(bad))
    assert _read_mock_pr_files("owner/repo", 7) is None


async def test_list_pr_files_uses_mock_and_skips_http(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``list_pr_files`` must short-circuit before any HTTP setup.

    To prove the network path is not taken, we replace ``AsyncClient``
    with a sentinel that raises on construction. The positive-control
    second assertion uses the SAME exploding client with a non-matching
    PR number — if the short-circuit weren't load-bearing, the network
    path would fire and the sentinel would raise.
    """
    fixture = _write_mock_file(tmp_path, {"o/r:42": ["x.ts", "y.py"]})
    monkeypatch.setenv("BODHI_MOCK_PR_FILES_PATH", str(fixture))

    exploded: list[tuple[object, object]] = []

    class _ExplodingClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            exploded.append((args, kwargs))
            raise AssertionError(
                "AsyncClient was constructed — short-circuit failed to prevent network setup"
            )

    monkeypatch.setattr("app.services.github_client.AsyncClient", _ExplodingClient)
    client = GitHubClient(pat="ignored")

    # Match path: mock fires, network path never entered.
    assert await client.list_pr_files("o/r", 42) == ["x.ts", "y.py"]
    assert exploded == [], "AsyncClient should not be constructed on a mock match"

    # Positive control: non-matching key falls through to the network
    # path. If the short-circuit weren't doing the work, the matching
    # path above would also reach AsyncClient and raise — so the fact
    # that the matching call succeeded AND this one raises proves the
    # short-circuit is what kept the network path closed.
    with pytest.raises(AssertionError, match="network setup"):
        await client.list_pr_files("o/r", 99)
