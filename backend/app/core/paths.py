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
``safe_join`` so the traversal check (``Path.is_relative_to``) is in one
place — CodeQL's ``py/path-injection`` query recognises this pattern as
a sanitiser, and centralising it keeps future call sites from
re-implementing a weaker variant (e.g. ``str.startswith``, which is
suffix-bypassable on symlinked or normalised paths).
"""

from pathlib import Path


class PathTraversalError(ValueError):
    """Raised when a caller-supplied path resolves outside its root."""


def safe_join(root: Path | str, relative: str) -> Path:
    """Join ``relative`` under ``root`` and verify the result stays inside.

    Resolves both sides to absolute, symlink-collapsed paths and asserts
    ``Path.is_relative_to(root)``. Raises :class:`PathTraversalError`
    when the joined path escapes — including via leading ``/`` (which
    would make ``Path(...)`` discard ``root``), ``..`` segments that
    climb above ``root``, or symlinks that point outside.

    Returns the resolved ``Path`` so callers can do file I/O against it
    without re-resolving.

    The ``relative`` argument must NOT be empty; callers that mean
    "the root itself" should pass ``root`` directly.
    """
    if not relative:
        raise PathTraversalError("relative path must not be empty")

    base = Path(root).resolve()
    candidate = (base / relative).resolve()
    if not candidate.is_relative_to(base):
        raise PathTraversalError(f"path {relative!r} escapes its root {str(base)!r}")
    return candidate
