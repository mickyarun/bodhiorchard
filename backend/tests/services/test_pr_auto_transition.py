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

"""Unit tests for the BUD-number extraction matcher.

Pins the accept / reject set of ``extract_bud_number`` so the regex
cannot regress silently. The matcher is the single seam between
PR-title / branch parsing and the BUD lookup — drifting on what counts
as a BUD reference would re-introduce either the pre-fix orphan rate
or false-positive links across BUDs.
"""

from __future__ import annotations

import pytest

from app.services.pr_auto_transition import (
    extract_all_bud_numbers,
    extract_bud_number,
    pr_references_bud,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Bare references — most common forms.
        ("BUD-8", 8),
        ("bud-008", 8),
        ("bud8", 8),
        ("BUD8", 8),
        # Branch-style separators.
        ("feat/BUD-7-rename", 7),
        ("bugfix/bud-12-x", 12),
        ("bud-001/feature-x", 1),
        # Title-style separators — full punctuation set users actually type.
        ("[BUD-12] Update X", 12),
        ("(bud-77) inline", 77),
        ("Fix the thing — BUD-3 follow up", 3),
        ("BUD-8 fix x", 8),
        ("Closes #BUD-4", 4),
        ("fix,BUD-3 quick", 3),
        ("revert: BUD-21 cleanup", 21),
        ("Notes; BUD-99 next", 99),
        (".BUD-2 release notes", 2),
        # First match wins when multiple are present.
        ("BUD-5 references BUD-9", 5),
    ],
)
def test_extract_bud_number_accepts_real_world_forms(text: str, expected: int) -> None:
    """Branches and titles users actually write should resolve."""
    assert extract_bud_number(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        # Mid-word: the leading ``-`` would falsely word-boundary under a naive
        # regex. The matcher must reject when the BUD prefix is preceded by a
        # letter rather than a separator.
        "auth-bud-7",
        "feature-prebud-2",
        # Glued to other digits.
        "bud2name",
        "abcbud-5",
        # No number.
        "feature/bud-x",
        "release/uat",
        # Nothing.
        "",
        " ",
    ],
)
def test_extract_bud_number_rejects_mid_word_and_garbage(text: str) -> None:
    """False-positives across BUDs would be worse than orphan PRs."""
    assert extract_bud_number(text) is None


def test_extract_bud_number_handles_none() -> None:
    """None input must not raise — webhook payload titles can be None."""
    assert extract_bud_number(None) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Release branches carrying several BUDs at once — the case the
        # release-stage tab content-filter needs to handle correctly.
        ("release/bud-001-bud-004-bud-007", {1, 4, 7}),
        ("release/2026-08-01 BUD-3 BUD-9", {3, 9}),
        # Single reference still works.
        ("feat/BUD-7-rename", {7}),
        ("[BUD-12]", {12}),
        # No reference.
        ("hotfix/auth", set()),
        ("", set()),
    ],
)
def test_extract_all_bud_numbers(text: str, expected: set[int]) -> None:
    """Multi-BUD branches must surface every BUD they reference."""
    assert extract_all_bud_numbers(text) == expected


@pytest.mark.parametrize(
    ("bud_number", "head_ref", "title", "expected"),
    [
        # Title carries this BUD — match.
        (4, "feature/processing-loader", "[BUD-004] processing loader", True),
        # Branch carries this BUD — match.
        (4, "bud-004/processing", "processing loader", True),
        # Release branch carries multiple including this one — match.
        (4, "release/bud-001-bud-004", "Release 2026-08-01", True),
        (1, "release/bud-001-bud-004", "Release 2026-08-01", True),
        # Release branch does NOT carry this BUD — no match (the bug
        # the user reported on the PROD tab).
        (4, "release/bud-001-bud-007", "Release 2026-08-01", False),
        # Unrelated PR to ``main`` with no BUD anywhere — no match
        # (this is the leaking case from the screenshot:
        # "ATOA-9396: remote payments — terminal (Dart) side").
        (4, "feature/atoa-9396-dart", "ATOA-9396: remote payments", False),
        # Either field can carry the reference.
        (4, None, "Closes #BUD-4", True),
        (4, "BUD-4/x", None, True),
        # Both None — no match.
        (4, None, None, False),
    ],
)
def test_pr_references_bud(
    bud_number: int,
    head_ref: str | None,
    title: str | None,
    expected: bool,
) -> None:
    """Stage-tab content filter pins the user's reported behaviour:
    only PRs whose head ref or title carry this BUD's number appear."""
    assert pr_references_bud(bud_number, head_ref, title) is expected


def test_pr_references_bud_with_space_form_in_title() -> None:
    """``Bud 004/...`` (with a space) does NOT match — the regex requires
    ``bud-?`` immediately followed by digits. Branch naming is the
    reliable link source; loose space-form titles need the developer
    to add a proper tag (``[BUD-004]``)."""
    assert pr_references_bud(4, None, "Bud 004/processing loader") is False
    assert pr_references_bud(4, "bud-004/processing-loader", "Bud 004/processing loader") is True
