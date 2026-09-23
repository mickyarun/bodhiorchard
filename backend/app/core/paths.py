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
import re
import unicodedata
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


_FILENAME_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]")
_REPEATED_UNDERSCORE_RE = re.compile(r"_+")


def sanitize_filename(name: str | None, *, fallback: str = "file") -> str:
    """Normalise a user-supplied filename to an ASCII-safe storage name.

    Used by every upload route that echoes a filename back in a
    ``Content-Disposition`` header or folds it into a storage path.
    Trusting the raw name leaves characters like `` `` (narrow
    no-break space, common in macOS screenshot names such as
    ``Screenshot 2026-05-20 at 4.00.01 PM.png``) in the value, which
    crashes downloads at the header-encode step with
    ``UnicodeEncodeError: 'latin-1' codec can't encode character``.
    Normalising at upload time keeps both the storage path AND the
    DB-stored filename strictly latin-1, so downloads never have to
    think about Unicode.

    NFKD decomposes accented chars into base + combining marks,
    ``encode("ascii", "ignore")`` then strips the combining marks
    (so "café" → "cafe", not "caf"). Whatever remains that isn't
    ``[A-Za-z0-9._-]`` becomes ``_``; runs of underscores collapse
    to one; an empty stem falls back to ``fallback``.

    Args:
        name: The client-supplied filename, possibly ``None``.
        fallback: Stem to use when nothing printable survives.

    Returns:
        An ASCII-safe ``stem.ext`` (or bare ``stem``) name.
    """
    base = os.path.basename(name or fallback)
    if not base:
        base = fallback

    stem, dot, ext = base.rpartition(".")
    if not dot:
        stem, ext = base, ""

    # NFKD → ASCII fold so "Café résumé.PDF" → "Cafe resume.PDF"
    stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode("ascii")
    ext = unicodedata.normalize("NFKD", ext).encode("ascii", "ignore").decode("ascii")

    # Replace remaining unsafe chars, collapse repeats, trim ``_``s
    stem = _FILENAME_UNSAFE_RE.sub("_", stem)
    stem = _REPEATED_UNDERSCORE_RE.sub("_", stem).strip("_")
    # Strip leading/trailing dots so all-dots inputs ("...", "..")
    # don't survive as path-traversal-looking segments. ``strip(".")``
    # AFTER underscore trimming handles ``__.__`` patterns too.
    stem = stem.strip(".")
    ext = _FILENAME_UNSAFE_RE.sub("", ext)[:10]  # cap extension length

    if not stem:
        stem = fallback
    return f"{stem}.{ext}" if ext else stem
