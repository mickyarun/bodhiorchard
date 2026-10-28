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

"""An in-memory ``api.github.com`` for one GitHub App installation.

Mounted on the :class:`FakeHttpRouter`, it serves the REST calls the app
makes: the App JWT → installation-token exchange (the JWT signature is
checked against the fake App's key), installable repos and branches with
``Link`` pagination, repo → installation lookup, pull requests, PR commits
and files, reviews, org members and user profiles. Installation-token calls
need a token the fake issued. ``fail()`` queues 401 / 404 / rate-limit
replies for any route.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field
from typing import Any

import httpx
import jwt

from tests.fakes.github_keys import app_key_pair
from tests.fakes.http_util import FaultPlan, InjectedFault, json_response, request_json

API_HOST = "api.github.com"
FIXED_EXPIRY = "2099-01-01T00:00:00Z"


@dataclass
class FakeGitHubRepo:
    """A repository visible to the installation."""

    full_name: str
    branches: dict[str, str] = field(default_factory=lambda: {"main": "a" * 40})
    private: bool = True
    default_branch: str = "main"
    pushed_at: str = "2026-01-02T03:04:05Z"


class FakeGitHub:
    """See the module docstring. All state is plain attributes a test can set."""

    def __init__(self, app_id: int = 1001, installation_id: int = 4242) -> None:
        self.app_id = app_id
        self.installation_id = installation_id
        self.app_slug = "glideship-test-app"
        self.private_key_pem, self._public_key_pem = app_key_pair()
        self.page_size = 2
        self.repos: dict[str, FakeGitHubRepo] = {}
        self.pulls: dict[tuple[str, int], dict[str, Any]] = {}
        self.pr_commits: dict[tuple[str, int], list[str]] = {}
        self.pr_files: dict[tuple[str, int], list[str]] = {}
        self.members: dict[str, dict[str, Any]] = {}
        self.issued_tokens: list[str] = []
        self.extra_tokens: set[str] = set()
        self.reviews: list[dict[str, Any]] = []
        self.requests: list[httpx.Request] = []
        self.faults = FaultPlan()
        self._ids = itertools.count(1)

    # ── test setup ────────────────────────────────────────────────
    def add_repo(self, full_name: str, *branches: str, private: bool = True) -> FakeGitHubRepo:
        """Make ``full_name`` visible to the installation with ``branches``."""
        names = branches or ("main",)
        shas = {name: f"{next(self._ids):040x}" for name in names}
        repo = FakeGitHubRepo(full_name, shas, private=private, default_branch=names[0])
        self.repos[full_name] = repo
        return repo

    def add_member(self, login: str, name: str | None = None, email: str | None = None) -> None:
        """Add an org member with a public profile."""
        self.members[login] = {"login": login, "name": name, "email": email}

    def fail(self, method: str, path_pattern: str, status: int, times: int = 1) -> None:
        """Answer the next ``times`` matching requests with ``status``."""
        body = {"message": {401: "Bad credentials", 404: "Not Found"}.get(status, "error")}
        self.faults.add(InjectedFault(method, path_pattern, status, body, {}, times))

    def rate_limit(self, method: str, path_pattern: str, times: int = 1) -> None:
        """Answer with GitHub's primary rate-limit 403."""
        headers = {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "4102444800"}
        body = {"message": "API rate limit exceeded"}
        self.faults.add(InjectedFault(method, path_pattern, 403, body, headers, times))

    # ── request handling ──────────────────────────────────────────
    def _bearer(self, request: httpx.Request) -> str:
        header = request.headers.get("authorization", "")
        return header.split(" ", 1)[1] if " " in header else ""

    def _app_jwt_ok(self, request: httpx.Request) -> bool:
        try:
            claims = jwt.decode(self._bearer(request), self._public_key_pem, algorithms=["RS256"])
        except jwt.PyJWTError:
            return False
        return str(claims.get("iss")) == str(self.app_id)

    def _token_ok(self, request: httpx.Request) -> bool:
        token = self._bearer(request)
        return token in self.issued_tokens or token in self.extra_tokens

    def _page(self, request: httpx.Request, items: list[Any], key: str | None) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        start = (page - 1) * self.page_size
        chunk = items[start : start + self.page_size]
        headers: dict[str, str] = {}
        if start + self.page_size < len(items):
            nxt = request.url.copy_merge_params({"page": str(page + 1)})
            headers["Link"] = f'<{nxt}>; rel="next"'
        body: Any = {"total_count": len(items), key: chunk} if key else chunk
        return json_response(200, body, headers)

    def handle(self, request: httpx.Request) -> httpx.Response:
        """Serve one request (mount this on the router for ``api.github.com``)."""
        self.requests.append(request)
        injected = self.faults.take(request)
        if injected is not None:
            return injected
        path = request.url.path
        if path == "/app" or path.startswith("/app/"):
            return self._app_routes(request, path)
        if not self._token_ok(request):
            return json_response(401, {"message": "Bad credentials"})
        return self._token_routes(request, path)

    def _app_routes(self, request: httpx.Request, path: str) -> httpx.Response:
        if not self._app_jwt_ok(request):
            return json_response(401, {"message": "A JSON web token could not be decoded"})
        if path == "/app":
            return json_response(200, {"id": self.app_id, "slug": self.app_slug})
        match = re.fullmatch(r"/app/installations/(\d+)/access_tokens", path)
        if match and request.method == "POST":
            if int(match.group(1)) != self.installation_id:
                return json_response(404, {"message": "Not Found"})
            token = f"ghs_fake{len(self.issued_tokens) + 1:04d}"
            self.issued_tokens.append(token)
            return json_response(201, {"token": token, "expires_at": FIXED_EXPIRY})
        return json_response(404, {"message": "Not Found"})

    def _token_routes(self, request: httpx.Request, path: str) -> httpx.Response:
        if path == "/installation/repositories":
            items = [self._repo_json(r) for r in self.repos.values()]
            return self._page(request, items, "repositories")
        if re.fullmatch(r"/orgs/[^/]+/members", path):
            return json_response(200, [{"login": m, "avatar_url": ""} for m in self.members])
        if match := re.fullmatch(r"/users/([^/]+)", path):
            member = self.members.get(match.group(1))
            return json_response(200, member) if member else json_response(404, {})
        match = re.fullmatch(r"/repos/([^/]+/[^/]+)(/.*)?", path)
        repo = self.repos.get(match.group(1)) if match else None
        if match is None or repo is None:
            return json_response(404, {"message": "Not Found"})
        return self._repo_routes(request, repo, match.group(2) or "")

    def _repo_routes(
        self, request: httpx.Request, repo: FakeGitHubRepo, rest: str
    ) -> httpx.Response:
        key = repo.full_name
        if rest == "/installation":
            return json_response(200, {"id": self.installation_id})
        if rest == "/branches":
            items = [{"name": n, "commit": {"sha": s}} for n, s in repo.branches.items()]
            return self._page(request, items, None)
        if rest == "/pulls" and request.method == "GET":
            return json_response(200, [p for (r, _), p in self.pulls.items() if r == key])
        if rest == "/pulls" and request.method == "POST":
            return json_response(201, self._create_pull(key, request_json(request)))
        if match := re.fullmatch(r"/pulls/(\d+)/(commits|files|reviews)", rest):
            number, kind = int(match.group(1)), match.group(2)
            if kind == "commits":
                shas = self.pr_commits.get((key, number), [])
                return json_response(200, [{"sha": sha} for sha in shas])
            if kind == "files":
                files = self.pr_files.get((key, number), [])
                return json_response(200, [{"filename": f, "status": "modified"} for f in files])
            review = {"id": next(self._ids), "pull": number, **request_json(request)}
            self.reviews.append(review)
            return json_response(200, review)
        return json_response(404, {"message": "Not Found"})

    def _create_pull(self, full_name: str, body: dict[str, Any]) -> dict[str, Any]:
        number = next(self._ids)
        pull = {
            "number": number,
            "state": "open",
            "title": body.get("title", ""),
            "html_url": f"https://github.com/{full_name}/pull/{number}",
            "head": {"ref": body.get("head")},
            "base": {"ref": body.get("base")},
        }
        self.pulls[(full_name, number)] = pull
        return pull

    def _repo_json(self, repo: FakeGitHubRepo) -> dict[str, Any]:
        owner, name = repo.full_name.split("/", 1)
        return {
            "full_name": repo.full_name,
            "name": name,
            "owner": {"login": owner},
            "private": repo.private,
            "default_branch": repo.default_branch,
            "pushed_at": repo.pushed_at,
            "clone_url": f"https://github.com/{repo.full_name}.git",
        }
