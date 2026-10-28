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
makes. Auth follows GitHub: ``/app/*`` and ``/repos/{x}/installation`` need
an App JWT signed with the fake App's private key (signature and ``iss``
are checked); everything else needs an installation token the fake issued
(or a PAT added to ``extra_tokens``). Repo routes live in
:mod:`.github_repos`. ``fail()`` / ``rate_limit()`` queue error replies.
"""

from __future__ import annotations

import itertools
import re

import httpx
import jwt

from tests.fakes.github_keys import app_key_pair
from tests.fakes.github_repos import FakeGitHubRepo, RepoRoutes
from tests.fakes.http_util import FaultPlan, InjectedFault, json_response

API_HOST = "api.github.com"
FIXED_EXPIRY = "2099-01-01T00:00:00Z"


class FakeGitHub(RepoRoutes):
    """See the module docstring. All state is plain attributes a test can set."""

    def __init__(
        self,
        app_id: int = 1001,
        installation_id: int = 4242,
        key_pair: tuple[str, str] | None = None,
    ) -> None:
        super().__init__()
        self.app_id = app_id
        self.installation_id = installation_id
        self.app_slug = "glideship-test-app"
        self.private_key_pem, self._public_key_pem = key_pair or app_key_pair()
        self.members: dict[str, dict[str, object]] = {}
        self.issued_tokens: list[str] = []
        self.extra_tokens: set[str] = set()
        self.requests: list[httpx.Request] = []
        self.responses: list[tuple[str, int]] = []
        self.faults = FaultPlan()
        self._shas = itertools.count(1)

    # ── test setup ────────────────────────────────────────────────
    def add_repo(self, full_name: str, *branches: str, private: bool = True) -> FakeGitHubRepo:
        """Make ``full_name`` visible to the installation with ``branches``."""
        names = branches or ("main",)
        shas = {name: f"{next(self._shas):040x}" for name in names}
        repo_id = 500_000 + len(self.repos)
        repo = FakeGitHubRepo(full_name, repo_id, shas, private, names[0])
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

    def handle(self, request: httpx.Request) -> httpx.Response:
        """Serve one request (mount this on the router for ``api.github.com``)."""
        self.requests.append(request)
        response = self.faults.take(request) or self._route(request)
        self.responses.append((request.url.path, response.status_code))
        return response

    def _route(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/app" or path.startswith("/app/") or path.endswith("/installation"):
            return self._app_routes(request, path)
        if not self._token_ok(request):
            return json_response(401, {"message": "Bad credentials"})
        if re.fullmatch(r"/orgs/[^/]+/members", path):
            return json_response(200, [{"login": m, "avatar_url": ""} for m in self.members])
        if match := re.fullmatch(r"/users/([^/]+)", path):
            member = self.members.get(match.group(1))
            return json_response(200, member) if member else json_response(404, {})
        return self.repo_route(request, path)

    def _app_routes(self, request: httpx.Request, path: str) -> httpx.Response:
        if not self._app_jwt_ok(request):
            return json_response(401, {"message": "A JSON web token could not be decoded"})
        if path == "/app":
            return json_response(200, {"id": self.app_id, "slug": self.app_slug})
        if match := re.fullmatch(r"/repos/([^/]+/[^/]+)/installation", path):
            if match.group(1) not in self.repos:
                return json_response(404, {"message": "Not Found"})
            return json_response(200, {"id": self.installation_id, "app_id": self.app_id})
        match = re.fullmatch(r"/app/installations/(\d+)/access_tokens", path)
        if match and request.method == "POST":
            if int(match.group(1)) != self.installation_id:
                return json_response(404, {"message": "Not Found"})
            token = f"ghs_fake{len(self.issued_tokens) + 1:04d}"
            self.issued_tokens.append(token)
            return json_response(201, {"token": token, "expires_at": FIXED_EXPIRY})
        return json_response(404, {"message": "Not Found"})
