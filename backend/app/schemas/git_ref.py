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

"""Branch-name validation shared by every schema that accepts one.

A stored branch name ends up as a git argument and as a directory name
(the scan worktree folder is named after the main branch), so it is held
to the same rules as ``git check-ref-format --branch``. A name like
``..`` would otherwise point the scan worktree at its shared parent.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, Field

# Matches ``String(100)`` on the tracked-repository branch columns.
BRANCH_NAME_MAX_LENGTH = 100

_FORBIDDEN_CHARS = frozenset(" ~^:?*[\\")
_FORBIDDEN_SEQUENCES = ("..", "//", "@{")


def branch_name_problem(name: str) -> str | None:
    """Return why ``name`` isn't a valid branch name, or ``None`` if it is."""
    if not name:
        return "must not be empty"
    if name == "@":
        return "must not be '@'"
    if name.startswith("-"):
        return "must not start with '-'"
    if name.startswith("/") or name.endswith("/"):
        return "must not start or end with '/'"
    if name.endswith("."):
        return "must not end with '.'"
    for seq in _FORBIDDEN_SEQUENCES:
        if seq in name:
            return f"must not contain {seq!r}"
    for char in name:
        if ord(char) < 0x20 or ord(char) == 0x7F or char in _FORBIDDEN_CHARS:
            return f"must not contain {char!r}"
    for component in name.split("/"):
        if component.startswith("."):
            return "no '/'-separated part may start with '.'"
        if component.endswith(".lock"):
            return "no '/'-separated part may end with '.lock'"
    return None


def _check_branch_name(name: str) -> str:
    problem = branch_name_problem(name)
    if problem is not None:
        raise ValueError(f"invalid branch name: {problem}")
    return name


BranchName = Annotated[
    str,
    Field(max_length=BRANCH_NAME_MAX_LENGTH),
    AfterValidator(_check_branch_name),
]
"""A git branch name that passes ``git check-ref-format --branch``."""
