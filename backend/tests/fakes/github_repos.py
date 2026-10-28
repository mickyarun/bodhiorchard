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

"""Installation-token routes of the fake GitHub: repos, branches and pull requests.

Lists are paginated like GitHub: ``per_page`` (default 30, at most
``max_page_size``, 100 like GitHub), with a ``Link: <…>; rel="next"`` header
while more pages remain. Lower ``max_page_size`` to force several pages, but
only for callers that follow ``Link``: callers that stop at the first short
page would stop early, exactly as they would against a server that did that. ``GET /pulls``
honours ``state``, ``base`` and ``head`` (``owner:branch``, as GitHub
requires), and opening a second open PR for the same head answers 422.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from typing import Any

import httpx

from tests.fakes.http_util import json_response, request_json


@dataclass
class FakeGitHubRepo:
    """A repository visible to the installation."""

    full_name: str
    id: int
    branches: dict[str, str]
    private: bool = True
    default_branch: str = "main"
    pushed_at: str = "2026-01-02T03:04:05Z"

    def as_json(self) -> dict[str, Any]:
        """The repository object as the REST API returns it."""
        owner, name = self.full_name.split("/", 1)
        return {
            "id": self.id,
            "full_name": self.full_name,
            "name": name,
            "owner": {"login": owner},
            "private": self.private,
            "default_branch": self.default_branch,
            "pushed_at": self.pushed_at,
            "clone_url": f"https://github.com/{self.full_name}.git",
        }


class RepoRoutes:
    """Mixin holding repo state and the token-authenticated repo routes."""

    def __init__(self) -> None:
        self.max_page_size = 100
        self.repos: dict[str, FakeGitHubRepo] = {}
        self.pulls: dict[tuple[str, int], dict[str, Any]] = {}
        self.pr_commits: dict[tuple[str, int], list[str]] = {}
        self.pr_files: dict[tuple[str, int], list[str]] = {}
        self.reviews: list[dict[str, Any]] = []
        self._pr_numbers = itertools.count(1)
        self._review_ids = itertools.count(9001)

    def page(self, request: httpx.Request, items: list[Any], key: str | None) -> httpx.Response:
        """One page of ``items`` with a ``Link`` header while more remain."""
        params = request.url.params
        size = min(int(params.get("per_page", "30")), self.max_page_size)
        number = int(params.get("page", "1"))
        start = (number - 1) * size
        headers: dict[str, str] = {}
        if start + size < len(items):
            nxt = request.url.copy_merge_params({"page": str(number + 1)})
            headers["Link"] = f'<{nxt}>; rel="next"'
        chunk = items[start : start + size]
        body: Any = {"total_count": len(items), key: chunk} if key else chunk
        return json_response(200, body, headers)

    def repo_route(self, request: httpx.Request, path: str) -> httpx.Response:
        """Dispatch ``/installation/repositories`` and ``/repos/{owner}/{name}/…``."""
        if path == "/installation/repositories":
            items = [repo.as_json() for repo in self.repos.values()]
            return self.page(request, items, "repositories")
        match = re.fullmatch(r"/repos/([^/]+/[^/]+)(/.*)?", path)
        repo = self.repos.get(match.group(1)) if match else None
        if match is None or repo is None:
            return json_response(404, {"message": "Not Found"})
        rest, key = match.group(2) or "", repo.full_name
        if rest == "/branches":
            items = [{"name": n, "commit": {"sha": s}} for n, s in repo.branches.items()]
            return self.page(request, items, None)
        if rest == "/pulls":
            if request.method == "POST":
                return self._create_pull(key, request_json(request))
            return json_response(200, self._list_pulls(key, request.url.params))
        if match := re.fullmatch(r"/pulls/(\d+)/(commits|files|reviews)", rest):
            return self._pull_detail(request, key, int(match.group(1)), match.group(2))
        return json_response(404, {"message": "Not Found"})

    def _pull_detail(
        self, request: httpx.Request, key: str, number: int, kind: str
    ) -> httpx.Response:
        if kind == "commits":
            shas = self.pr_commits.get((key, number), [])
            return self.page(request, [{"sha": sha} for sha in shas], None)
        if kind == "files":
            files = self.pr_files.get((key, number), [])
            return self.page(request, [{"filename": f, "status": "modified"} for f in files], None)
        review = {"id": next(self._review_ids), "pull": number, **request_json(request)}
        self.reviews.append(review)
        return json_response(200, review)

    def _list_pulls(self, key: str, params: httpx.QueryParams) -> list[dict[str, Any]]:
        state, base, head = params.get("state", "open"), params.get("base"), params.get("head")
        owner = key.split("/", 1)[0]
        found = []
        for (repo, _), pull in self.pulls.items():
            if repo != key or state not in ("all", pull["state"]):
                continue
            if base and pull["base"]["ref"] != base:
                continue
            if head and f"{owner}:{pull['head']['ref']}" != head:
                continue
            found.append(pull)
        return found

    def _create_pull(self, key: str, body: dict[str, Any]) -> httpx.Response:
        head = body.get("head")
        if any(p["head"]["ref"] == head and p["state"] == "open" for p in self._list_all(key)):
            errors = [{"message": f"A pull request already exists for {head}."}]
            return json_response(422, {"message": "Validation Failed", "errors": errors})
        number = next(self._pr_numbers)
        pull = {
            "number": number,
            "state": "open",
            "title": body.get("title", ""),
            "html_url": f"https://github.com/{key}/pull/{number}",
            "head": {"ref": head},
            "base": {"ref": body.get("base")},
        }
        self.pulls[(key, number)] = pull
        return json_response(201, pull)

    def _list_all(self, key: str) -> list[dict[str, Any]]:
        return [pull for (repo, _), pull in self.pulls.items() if repo == key]
