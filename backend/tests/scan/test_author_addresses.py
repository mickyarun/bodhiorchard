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

"""Reading a git author's address: GitHub noreply logins and machine identities."""

from __future__ import annotations

import pytest

from app.services.scan.author_addresses import github_noreply_login, is_machine_local
from app.services.scan.author_resolution import auto_create_enabled


@pytest.mark.parametrize(
    ("email", "login"),
    [
        ("12345+OctoCat@users.noreply.github.com", "octocat"),
        ("octo-cat@users.noreply.github.com", "octo-cat"),
        (" 9+a1@Users.NoReply.GitHub.com ", "a1"),
        ("41898282+github-actions[bot]@users.noreply.github.com", None),
        ("12345+@users.noreply.github.com", None),
        ("12345+-bad@users.noreply.github.com", None),
        ("octocat@github.com", None),
        ("octocat@users.noreply.github.com.evil.test", None),
    ],
)
def test_github_noreply_login(email: str, login: str | None) -> None:
    assert github_noreply_login(email) == login


@pytest.mark.parametrize(
    ("email", "machine_local"),
    [
        ("dev@Some-MacBook-Pro.local", True),
        ("dev@build-box.localdomain", True),
        ("dev@localhost", True),
        ("dev@(none)", True),
        ("dev@buildbox", True),
        ("dev@", True),
        ("@example.test", True),
        ("not-an-address", True),
        ("dev@mail.example.test", False),
        ("12345+dev@users.noreply.github.com", False),
        ("dev@local.example.test", False),
    ],
)
def test_is_machine_local(email: str, machine_local: bool) -> None:
    assert is_machine_local(email) is machine_local


@pytest.mark.parametrize(
    ("scan_cfg", "enabled"),
    [({}, True), ({"auto_create_members": True}, True), ({"auto_create_members": False}, False)],
)
def test_auto_create_defaults_on(scan_cfg: dict[str, bool], enabled: bool) -> None:
    assert auto_create_enabled(scan_cfg) is enabled
