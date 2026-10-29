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

"""What a git author's address says about who they are.

Pure string checks, no database. A scan uses them to decide whether an
author it has never seen is a GitHub noreply address it can tie to a
member's login, or a machine's default identity that no person owns.
"""

from __future__ import annotations

import re

_NOREPLY_DOMAIN = "users.noreply.github.com"
# ``12345+login`` (current form) or bare ``login`` (accounts older than 2017).
# Logins are letters, digits and inner hyphens; ``[bot]`` accounts never match.
_NOREPLY_LOCAL_PART = re.compile(r"(?:\d+\+)?(?P<login>[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)")
# Hostname suffixes git falls back to when nobody set ``user.email``.
_MACHINE_LOCAL_SUFFIXES = (".local", ".localdomain")


def github_noreply_login(email: str) -> str | None:
    """The GitHub login a noreply address belongs to, lowercased; ``None`` otherwise."""
    local, _, domain = email.strip().lower().rpartition("@")
    if domain != _NOREPLY_DOMAIN:
        return None
    match = _NOREPLY_LOCAL_PART.fullmatch(local)
    return match.group("login") if match else None


def is_machine_local(email: str) -> bool:
    """Whether ``email`` is a machine's default identity rather than a mailbox.

    Git builds one from the user and host name when ``user.email`` is unset,
    giving ``name@Some-MacBook.local``, ``name@localhost`` or
    ``name@(none)``. Such a domain has no dot or ends in a local suffix.
    """
    local, at, domain = email.strip().lower().rpartition("@")
    if not at or not local:
        return True
    return "." not in domain or domain.endswith(_MACHINE_LOCAL_SUFFIXES)
