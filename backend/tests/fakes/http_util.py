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

"""Small shared pieces for the HTTP fakes: JSON replies and error injection."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx


def json_response(status: int, body: Any, headers: dict[str, str] | None = None) -> httpx.Response:
    """A JSON ``httpx.Response`` with ``status``."""
    return httpx.Response(status, json=body, headers=headers or {})


def request_json(request: httpx.Request) -> dict[str, Any]:
    """The request's JSON body, or form fields, as a dict (empty when none)."""
    raw = request.content
    if not raw:
        return {}
    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" in content_type:
        return dict(httpx.QueryParams(raw.decode()))
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else {"_": parsed}


@dataclass
class InjectedFault:
    """A canned reply served instead of the fake's normal answer."""

    method: str
    path_pattern: str
    status: int
    body: Any = None
    headers: dict[str, str] = field(default_factory=dict)
    times: int = 1

    def matches(self, request: httpx.Request) -> bool:
        """True for a request this fault should answer."""
        if self.method not in ("*", request.method):
            return False
        return re.search(self.path_pattern, request.url.path) is not None


@dataclass
class FaultPlan:
    """Faults queued by a test; each answers ``times`` requests then expires."""

    faults: list[InjectedFault] = field(default_factory=list)

    def add(self, fault: InjectedFault) -> None:
        """Queue ``fault``."""
        self.faults.append(fault)

    def take(self, request: httpx.Request) -> httpx.Response | None:
        """The canned reply for ``request``, consuming one use of the fault."""
        for fault in self.faults:
            if fault.matches(request):
                fault.times -= 1
                if fault.times <= 0:
                    self.faults.remove(fault)
                return json_response(fault.status, fault.body, dict(fault.headers))
        return None
