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
"""

from pathlib import Path, PurePosixPath


class PathTraversalError(ValueError):
    """Raised when a caller-supplied path resolves outside its root."""


def _has_traversal_components(relative: str) -> bool:
    """Return True when ``relative`` contains ``..`` or is absolute.

    Pure string-level inspection — no filesystem I/O. This runs BEFORE
    any ``Path.resolve()`` call so symlink-following never happens on
    unsanitised input. Uses ``PurePosixPath`` to split on both ``/``
    and ``\\`` independent of the host platform.
    """
    if relative.startswith(("/", "\\")):
        return True
    parts = PurePosixPath(relative.replace("\\", "/")).parts
    return any(part == ".." for part in parts)


def safe_join(root: Path | str, relative: str) -> Path:
    """Join ``relative`` under ``root`` and verify the result stays inside.

    Two layered guards:

      1. String-level ``..`` / leading-``/`` rejection BEFORE any
         filesystem touch — this is the path-injection sanitiser that
         static analysers (incl. CodeQL ``py/path-injection``)
         recognise on the data-flow path.
      2. Post-resolve ``Path.is_relative_to(root)`` — catches symlink
         escapes that survive step 1 (e.g. a directory entry inside
         ``root`` that symlinks outside it).

    Returns the resolved ``Path`` so callers can do file I/O against it
    without re-resolving.

    The ``relative`` argument must NOT be empty; callers meaning "the
    root itself" should use ``root`` directly.
    """
    if not relative:
        raise PathTraversalError("relative path must not be empty")
    if _has_traversal_components(relative):
        raise PathTraversalError(f"path {relative!r} contains traversal components")

    base = Path(root).resolve()
    candidate = (base / relative).resolve()
    if not candidate.is_relative_to(base):
        raise PathTraversalError(f"path {relative!r} escapes its root {str(base)!r}")
    return candidate
