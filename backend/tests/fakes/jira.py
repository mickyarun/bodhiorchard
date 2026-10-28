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

"""An in-memory Jira Cloud site for ``JiraClient``.

Mounted on the :class:`FakeHttpRouter` for ``*.atlassian.net``. Requests must
carry the Basic credentials the fake was built with, otherwise 401. Serves
``serverInfo``, project search, project statuses, single issues, the field
list and ``/search/jql`` with ``nextPageToken`` cursor pagination
(``page_size`` issues per page, filtered on ``project = KEY``). ``fail()``
queues 401 / 403 / 429 / 5xx replies; 429 carries ``Retry-After: 0`` so the
client's backoff does not slow the test down.
"""

from __future__ import annotations

import base64
import re
import zlib
from typing import Any

import httpx

from tests.fakes.http_util import FaultPlan, InjectedFault, json_response

SITE_URL = "https://acme-test.atlassian.net"
API = "/rest/api/3"


def jira_issue(
    key: str,
    summary: str,
    *,
    issue_type: str = "Story",
    status: str = "To Do",
    description: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """An issue in the REST v3 shape, ``description`` as a one-paragraph ADF doc."""
    adf = None
    if description is not None:
        paragraph = {"type": "paragraph", "content": [{"type": "text", "text": description}]}
        adf = {"type": "doc", "version": 1, "content": [paragraph]}
    body = {
        "summary": summary,
        "issuetype": {"name": issue_type},
        "status": {"name": status, "statusCategory": {"key": "new"}},
        "description": adf,
        "project": {"key": key.split("-", 1)[0]},
        "labels": [],
        "created": "2026-01-01T00:00:00.000+0000",
        "updated": "2026-01-02T00:00:00.000+0000",
        **fields,
    }
    return {"id": str(zlib.crc32(key.encode()) % 100_000), "key": key, "fields": body}


class FakeJira:
    """See the module docstring."""

    def __init__(self, email: str = "pm@acme.dev", api_token: str = "jira-token") -> None:
        creds = base64.b64encode(f"{email}:{api_token}".encode()).decode()
        self._expected_auth = f"Basic {creds}"
        self.site_url = SITE_URL
        self.email = email
        self.api_token = api_token
        self.page_size = 2
        self.projects: dict[str, str] = {}
        self.issues: list[dict[str, Any]] = []
        self.fields: list[dict[str, Any]] = [
            {"id": "summary", "name": "Summary", "custom": False},
            {"id": "customfield_10016", "name": "Story Points", "custom": True},
        ]
        self.statuses = ["To Do", "In Progress", "Done"]
        self.requests: list[httpx.Request] = []
        self.faults = FaultPlan()

    def add_issue(self, issue: dict[str, Any]) -> None:
        """Add an issue (its project is registered on the way)."""
        project = issue["key"].split("-", 1)[0]
        self.projects.setdefault(project, f"Project {project}")
        self.issues.append(issue)

    def fail(self, path_pattern: str, status: int, times: int = 1) -> None:
        """Answer the next ``times`` matching requests with ``status``."""
        headers = {"Retry-After": "0"} if status == 429 else {}
        body = {"errorMessages": [f"fake failure {status}"], "errors": {}}
        self.faults.add(InjectedFault("*", path_pattern, status, body, headers, times))

    def handle(self, request: httpx.Request) -> httpx.Response:
        """Serve one request (mount on the router for ``*.atlassian.net``)."""
        self.requests.append(request)
        injected = self.faults.take(request)
        if injected is not None:
            return injected
        if request.headers.get("authorization") != self._expected_auth:
            return json_response(401, {"errorMessages": ["Client must be authenticated"]})
        path = request.url.path.removeprefix(API)
        params = request.url.params
        if path == "/serverInfo":
            return json_response(200, {"baseUrl": self.site_url, "serverTitle": "Fake Jira"})
        if path == "/project/search":
            values = [{"key": k, "name": n} for k, n in self.projects.items()]
            return json_response(200, {"values": values, "isLast": True})
        if path == "/field":
            return json_response(200, self.fields)
        if path == "/search/jql":
            return self._search(params.get("jql", ""), params.get("nextPageToken"))
        if match := re.fullmatch(r"/issue/([A-Z][A-Z0-9]*-\d+)", path):
            found = [i for i in self.issues if i["key"] == match.group(1)]
            return json_response(200, found[0]) if found else json_response(404, {})
        if match := re.fullmatch(r"/project/([A-Z][A-Z0-9]*)/statuses", path):
            statuses = [{"name": name} for name in self.statuses]
            return json_response(200, [{"name": "Story", "statuses": statuses}])
        return json_response(404, {"errorMessages": ["Not found"]})

    def _search(self, jql: str, token: str | None) -> httpx.Response:
        project = re.search(r"project\s*=\s*\"?([A-Z][A-Z0-9]*)", jql)
        matching = [
            i
            for i in self.issues
            if project is None or i["key"].startswith(project.group(1) + "-")
        ]
        start = int(token) if token else 0
        page = matching[start : start + self.page_size]
        body: dict[str, Any] = {"issues": page, "isLast": start + self.page_size >= len(matching)}
        if start + self.page_size < len(matching):
            body["nextPageToken"] = str(start + self.page_size)
        return json_response(200, body)
