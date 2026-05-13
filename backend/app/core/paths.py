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

"""Filesystem-path safety helpers.

Centralises the "join a caller-supplied path component under a trusted
root without letting it escape" primitive. Every service that resolves
a user-controlled string into a real filesystem path should go through
``safe_join`` so the traversal check is in one place; future call sites
can't re-implement a weaker variant.

The implementation uses ``os.path.realpath`` + ``os.path.commonpath``
because that pair is the CodeQL-recognised sanitiser for
``py/path-injection`` — ``realpath`` collapses ``..`` and follows
symlinks, then ``commonpath`` compares against the trusted root.
"""

import os.path
from pathlib import Path


class PathTraversalError(ValueError):
    """Raised when a caller-supplied path resolves outside its root."""


def safe_join(root: Path | str, relative: str) -> Path:
    """Join ``relative`` under ``root`` and verify the result stays inside.

    Uses ``os.path.realpath`` to collapse ``..`` segments and follow
    symlinks to their final target, then ``os.path.commonpath`` to
    confirm the resolved path is still nested under the resolved
    ``root``. This catches both:

      - ``..`` traversal in the caller input (e.g. ``"a/../../etc"``).
      - Symlink escape (e.g. a directory entry inside ``root`` that
        points at ``/etc``).

    Returns the resolved ``Path`` so callers can perform I/O without
    re-resolving. ``relative`` must NOT be empty; callers meaning
    "the root itself" should use ``root`` directly.
    """
    if not relative:
        raise PathTraversalError("relative path must not be empty")

    base = os.path.realpath(str(root))
    candidate = os.path.realpath(os.path.join(base, relative))
    try:
        common = os.path.commonpath([base, candidate])
    except ValueError as exc:
        raise PathTraversalError(f"path {relative!r} escapes its root {base!r}") from exc
    if common != base:
        raise PathTraversalError(f"path {relative!r} escapes its root {base!r}")
    return Path(candidate)
