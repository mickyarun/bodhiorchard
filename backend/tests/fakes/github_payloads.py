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

"""GitHub webhook payloads shaped like the real deliveries.

Only the fields the app reads are filled; ids are deterministic from the
inputs so two calls with the same arguments build the same payload (a
redelivery). Sign them with :func:`tests.fakes.signing.signed_github_webhook`.
"""

from __future__ import annotations

import zlib
from typing import Any


def _repo(full_name: str) -> dict[str, Any]:
    owner, name = full_name.split("/", 1)
    repo_id = zlib.crc32(full_name.encode())
    return {"id": repo_id, "full_name": full_name, "name": name, "owner": {"login": owner}}


def pull_request_event(
    full_name: str,
    number: int,
    *,
    action: str = "closed",
    merged: bool = True,
    base: str = "main",
    head: str = "feature/work",
    head_sha: str = "1" * 40,
    merge_commit_sha: str | None = "2" * 40,
    base_sha: str = "3" * 40,
    title: str = "Ship the work",
    body: str | None = None,
    author: str = "octo-dev",
) -> dict[str, Any]:
    """A ``pull_request`` delivery (defaults: a PR merged into ``main``)."""
    pull = {
        "id": 10_000 + number,
        "number": number,
        "title": title,
        "body": body,
        "html_url": f"https://github.com/{full_name}/pull/{number}",
        "state": "closed" if action == "closed" else "open",
        "merged": merged,
        "merged_at": "2026-10-01T12:00:00Z" if merged else None,
        "merge_commit_sha": merge_commit_sha if merged else None,
        "head": {"ref": head, "sha": head_sha},
        "base": {"ref": base, "sha": base_sha},
        "user": {"login": author, "id": 7},
    }
    return {
        "action": action,
        "number": number,
        "pull_request": pull,
        "repository": _repo(full_name),
        "sender": {"login": author, "id": 7},
    }


def installation_event(
    action: str, app_id: int, installation_id: int, *repos: str
) -> dict[str, Any]:
    """An ``installation`` delivery (``created``, ``deleted``, ``suspend``…)."""
    return {
        "action": action,
        "installation": {"id": installation_id, "app_id": app_id, "account": {"login": "acme"}},
        "repositories": [{"full_name": name, "name": name.split("/")[-1]} for name in repos],
        "sender": {"login": "octo-admin", "id": 1},
    }
