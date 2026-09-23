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

"""Tests for the per-surface upload policies.

Covers the bug-attachment policy's extension gate (the rule that keeps
browser-supplied ``Content-Type`` out of the decision), the size and
count caps, and the QA-evidence policy's unchanged MIME-driven
behaviour — the latter guards against the refactor that introduced
policies having quietly widened what QA evidence accepts.
"""

from __future__ import annotations

import pytest

from app.services.file_storage import ALLOWED_MIME_TYPES, MAX_FILE_SIZE
from app.services.upload_policy import (
    QA_EVIDENCE_POLICY,
    UploadPolicyError,
    bug_attachment_policy,
)


def _policy(max_file_mb: int = 10, max_files: int = 10):
    """Build a bug-attachment policy with overridable limits."""
    return bug_attachment_policy(max_file_mb=max_file_mb, max_files=max_files)


# ── Extension gate ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("screenshot.png", "image/png"),
        ("photo.jpg", "image/jpeg"),
        ("photo.jpeg", "image/jpeg"),
        ("report.pdf", "application/pdf"),
        ("legacy.xls", "application/vnd.ms-excel"),
        (
            "export.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
    ],
)
def test_resolve_mime_accepts_every_supported_type(filename: str, expected: str) -> None:
    """Each advertised extension resolves to its canonical MIME type."""
    assert _policy().resolve_mime(filename) == expected


@pytest.mark.parametrize("filename", ["SHOUTING.PNG", "Report.Pdf", "Export.XLSX"])
def test_resolve_mime_is_case_insensitive(filename: str) -> None:
    """Extensions match regardless of case — macOS and Windows both vary it."""
    assert _policy().resolve_mime(filename)


@pytest.mark.parametrize(
    "filename",
    [
        "payload.exe",
        "notes.txt",
        "archive.zip",
        "page.html",
        "clip.mp4",
        "no_extension",
        "trailing.",
        "sneaky.png.exe",  # double extension — only the last one counts
    ],
)
def test_resolve_mime_rejects_unsupported_types(filename: str) -> None:
    """Anything off the list raises, with the allowed set in the message."""
    with pytest.raises(UploadPolicyError, match=r"\.pdf"):
        _policy().resolve_mime(filename)


def test_resolve_mime_ignores_client_content_type() -> None:
    """A ``.xlsx`` resolves to the spreadsheet type no matter what the browser said.

    This is the whole point of the extension-driven policy: browsers
    routinely send ``application/octet-stream`` for Office files, so a
    MIME allowlist would reject real spreadsheets at random.
    """
    policy = _policy()
    resolved = policy.resolve_mime("export.xlsx")
    assert resolved in policy.mime_types
    # And the derived type is what storage validation then accepts.
    policy.validate(b"data", resolved)


def test_validate_rejects_a_type_outside_the_policy() -> None:
    """The storage-layer backstop still refuses an unlisted content type."""
    with pytest.raises(UploadPolicyError, match="not allowed"):
        _policy().validate(b"data", "text/html")


# ── Size and count caps ──────────────────────────────────────────────


def test_check_size_allows_a_file_exactly_at_the_limit() -> None:
    """The cap is inclusive — a file of exactly N MB is accepted."""
    policy = _policy(max_file_mb=2)
    policy.check_size(2 * 1024 * 1024)


def test_check_size_rejects_one_byte_over() -> None:
    """One byte past the cap raises, naming the limit in MB."""
    policy = _policy(max_file_mb=2)
    with pytest.raises(UploadPolicyError, match="2 MB limit"):
        policy.check_size(2 * 1024 * 1024 + 1)


def test_check_count_allows_up_to_the_limit() -> None:
    """A bug one file below the cap can still take another."""
    _policy(max_files=3).check_count(2)


def test_check_count_rejects_at_the_limit() -> None:
    """At the cap the next upload is refused before any bytes are read."""
    with pytest.raises(UploadPolicyError, match="Limit of 3"):
        _policy(max_files=3).check_count(3)


def test_org_limits_flow_into_the_policy() -> None:
    """Per-org settings are what the policy enforces, not shipped defaults."""
    policy = bug_attachment_policy(max_file_mb=25, max_files=4)
    assert policy.max_bytes == 25 * 1024 * 1024
    assert policy.max_mb == 25
    assert policy.max_files == 4


def test_accepted_extensions_are_reported_sorted() -> None:
    """The client-facing extension list is stable and complete."""
    assert _policy().describe_extensions() == ".jpeg, .jpg, .pdf, .png, .xls, .xlsx"


# ── QA evidence is unchanged by the refactor ─────────────────────────


def test_qa_evidence_policy_still_backs_the_legacy_constants() -> None:
    """``file_storage``'s re-exports resolve to the QA policy's values."""
    assert MAX_FILE_SIZE == QA_EVIDENCE_POLICY.max_bytes == 10 * 1024 * 1024
    assert QA_EVIDENCE_POLICY.mime_types == ALLOWED_MIME_TYPES


@pytest.mark.parametrize("mime", ["image/png", "application/pdf", "video/mp4", "text/plain"])
def test_qa_evidence_policy_accepts_its_original_types(mime: str) -> None:
    """Every type QA evidence accepted before policies existed still passes."""
    QA_EVIDENCE_POLICY.validate(b"data", mime)


def test_qa_evidence_did_not_inherit_spreadsheets() -> None:
    """Widening bug attachments must not widen QA evidence.

    The regression this guards: appending Excel types to the one global
    allowlist instead of giving each surface its own policy.
    """
    with pytest.raises(UploadPolicyError, match="not allowed"):
        QA_EVIDENCE_POLICY.validate(b"data", "application/vnd.ms-excel")


def test_qa_evidence_policy_has_no_extension_gate() -> None:
    """It resolves nothing from filenames — it trusts the client's type."""
    assert QA_EVIDENCE_POLICY.extensions is None
    with pytest.raises(UploadPolicyError):
        QA_EVIDENCE_POLICY.resolve_mime("shot.png")
