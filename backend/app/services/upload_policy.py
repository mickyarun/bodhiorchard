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

"""What each upload surface accepts — size, count, and file type.

:class:`FileStorage` knows *where* bytes go; this module knows *what is
allowed through*. Splitting them means a new upload surface declares its
own rules instead of widening one global allowlist that every other
surface silently inherits — adding spreadsheets to bug attachments must
not also let spreadsheets into QA evidence.

Two policy shapes:

- **MIME-driven** (QA evidence) — trusts the browser's ``Content-Type``
  and checks it against a set. Kept as-is for the surface that shipped
  with it.
- **Extension-driven** (bug attachments) — ignores the browser's
  ``Content-Type`` entirely and derives the canonical type from the
  filename extension. Browsers are unreliable here: the same ``.xlsx``
  arrives as ``application/vnd.openxmlformats-...`` on one machine and
  ``application/octet-stream`` on another, so a MIME allowlist would
  reject legitimate spreadsheets at random. Deriving the type also
  means we serve back a value *we* chose rather than one the client
  supplied, so a file can't be uploaded as ``.png`` and served as
  ``text/html``.

Size caps are enforced twice on purpose: once when reading the request
body (so an oversized upload never fully lands in memory) and once here
before the bytes reach storage.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath

# Bug attachments: the formats a reporter realistically has to hand when
# filing — a screenshot, an exported log or data sheet, a signed-off PDF.
# Both Excel generations are accepted because "xls" colloquially covers
# both and rejecting a modern ``.xlsx`` would read as a bug.
BUG_ATTACHMENT_EXTENSIONS: Mapping[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".pdf": "application/pdf",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class UploadPolicyError(ValueError):
    """Raised when a file violates the policy of the surface it targets.

    Carries a message written for the person who picked the file, not
    for a log — API layers surface it verbatim as the 4xx ``detail``.
    """


@dataclass(frozen=True)
class UploadPolicy:
    """The size / count / type rules for one upload surface.

    Attributes:
        label: Human name of the surface ("Bug attachment"), used to
            open error messages so a 400 says what was rejected.
        max_bytes: Largest accepted single file.
        mime_types: Accepted content types. For extension-driven
            policies this is derived from ``extensions``.
        extensions: Lowercased ``.ext`` → canonical MIME map. ``None``
            means the policy trusts the client's content type instead.
        max_files: Cap on files attached to one parent record, or
            ``None`` for no cap. Enforced by the API layer, which is
            the only place that can count existing rows.
    """

    label: str
    max_bytes: int
    mime_types: frozenset[str]
    extensions: Mapping[str, str] | None = None
    max_files: int | None = None

    @classmethod
    def for_extensions(
        cls,
        *,
        label: str,
        max_bytes: int,
        extensions: Mapping[str, str],
        max_files: int | None = None,
    ) -> "UploadPolicy":
        """Build an extension-driven policy, deriving the MIME set from the map."""
        return cls(
            label=label,
            max_bytes=max_bytes,
            mime_types=frozenset(extensions.values()),
            extensions=extensions,
            max_files=max_files,
        )

    @property
    def max_mb(self) -> int:
        """The size cap in whole MB, for user-facing messages."""
        return self.max_bytes // (1024 * 1024)

    def describe_extensions(self) -> str:
        """Comma-separated accepted extensions, e.g. ``.jpg, .pdf, .xlsx``.

        Deduplicated and sorted so the message is stable — ``.jpg`` and
        ``.jpeg`` both map to JPEG but both are worth naming, whereas an
        unsorted dict order would make the text drift between releases.
        """
        if not self.extensions:
            return ", ".join(sorted(self.mime_types))
        return ", ".join(sorted(self.extensions))

    def resolve_mime(self, filename: str) -> str:
        """Return the canonical MIME type for ``filename``.

        Args:
            filename: The client-supplied name. Only its suffix is read,
                so a sanitised or raw name both work.

        Returns:
            The canonical content type to store and to serve back.

        Raises:
            UploadPolicyError: If this policy is not extension-driven,
                or the suffix is not on its list.
        """
        if self.extensions is None:
            raise UploadPolicyError(f"{self.label} does not resolve types from the filename.")
        suffix = PurePosixPath(filename).suffix.lower()
        mime = self.extensions.get(suffix)
        if mime is None:
            raise UploadPolicyError(f"{self.label}s must be one of: {self.describe_extensions()}.")
        return mime

    def check_size(self, size: int) -> None:
        """Raise :class:`UploadPolicyError` when ``size`` exceeds the cap."""
        if size > self.max_bytes:
            raise UploadPolicyError(f"{self.label} exceeds the {self.max_mb} MB limit.")

    def check_count(self, existing: int) -> None:
        """Raise when the parent record already holds ``max_files`` files."""
        if self.max_files is not None and existing >= self.max_files:
            raise UploadPolicyError(
                f"Limit of {self.max_files} {self.label.lower()}s reached. "
                "Delete one before adding another."
            )

    def validate(self, data: bytes, content_type: str) -> None:
        """Check raw bytes + content type against the policy.

        The storage-layer guard. API routes validate earlier and with
        better messages; this stays as the backstop so no future caller
        can write an unchecked file by skipping the route.

        Raises:
            UploadPolicyError: On oversize or disallowed content type.
        """
        self.check_size(len(data))
        if content_type not in self.mime_types:
            raise UploadPolicyError(
                f"Content type '{content_type}' is not allowed for "
                f"{self.label.lower()}s. Allowed: {', '.join(sorted(self.mime_types))}"
            )


# QA evidence — the original upload surface. Keeps its MIME-driven shape
# and its 10 MB cap; the values moved here from ``file_storage`` so that
# module re-exports them rather than owning a second copy.
QA_EVIDENCE_POLICY = UploadPolicy(
    label="QA evidence file",
    max_bytes=10 * 1024 * 1024,
    mime_types=frozenset(
        {
            "image/png",
            "image/jpeg",
            "image/gif",
            "image/webp",
            "application/pdf",
            "text/plain",
            "video/mp4",
            "video/webm",
        }
    ),
)


def bug_attachment_policy(*, max_file_mb: int, max_files: int) -> UploadPolicy:
    """Build the bug-attachment policy from an org's configured limits.

    Both caps are per-org (Settings → QA Automation & BUD Stages), so
    unlike :data:`QA_EVIDENCE_POLICY` this policy is constructed per
    request rather than being a module constant. The accepted file
    types are fixed — only the limits are tunable.

    Args:
        max_file_mb: Per-file size cap in MB, from the org's settings.
        max_files: Maximum attachments on a single bug.
    """
    return UploadPolicy.for_extensions(
        label="Bug attachment",
        max_bytes=max_file_mb * 1024 * 1024,
        extensions=BUG_ATTACHMENT_EXTENSIONS,
        max_files=max_files,
    )
