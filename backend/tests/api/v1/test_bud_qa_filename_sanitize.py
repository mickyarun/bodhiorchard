# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""Regression guards on ``_sanitize_filename``.

Production crash that prompted this: ``Screenshot 2026-05-20 at
4.00.01 PM.png`` (with the macOS-typed narrow no-break space `` ``
between "at" and "4") flowed straight into the
``Content-Disposition`` header. Starlette tried to ``encode("latin-1")``
the header value and the request 500'd.

Sanitising at upload time keeps both the storage path AND the
DB-stored ``filename`` strictly latin-1 — downloads never have to
think about Unicode. Tests pin:

  * The original failure shape now sanitises cleanly.
  * Accented characters fold to their ASCII base instead of dropping.
  * Extensions are preserved (mimetype inference depends on them).
  * Empty / None / extension-only inputs fall back to ``"evidence"``.
  * The result is always latin-1 encodable.
"""

from __future__ import annotations

import pytest

from app.api.v1.bud_qa import _sanitize_filename


def _latin1_ok(value: str) -> bool:
    try:
        value.encode("latin-1")
    except UnicodeEncodeError:
        return False
    return True


@pytest.mark.parametrize(
    "raw, expected",
    [
        # The exact production crash trigger.
        ("Screenshot 2026-05-20 at 4.00.01 PM.png", "Screenshot_2026-05-20_at_4.00.01_PM.png"),
        # Accented fold (NFKD): "Café résumé" → "Cafe resume".
        ("Café résumé.pdf", "Cafe_resume.pdf"),
        # CJK characters get stripped entirely; stem falls back.
        ("测试结果.png", "evidence.png"),
        # Whitespace runs collapse to a single ``_``.
        ("   spaces  everywhere   .txt", "spaces_everywhere.txt"),
        # Quoting / header-injection characters neutralised.
        ('evil"\r\n.png', "evil.png"),
        # Path-traversal characters neutralised.
        ("../../../etc/passwd", "passwd"),
        # No extension is OK.
        ("README", "README"),
        # Plain ASCII passes through unchanged.
        ("clean-name_v2.log", "clean-name_v2.log"),
    ],
)
def test_sanitize_filename_normalises_to_expected_form(raw: str, expected: str) -> None:
    assert _sanitize_filename(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "Screenshot 2026-05-20 at 4.00.01 PM.png",
        "🚀 rocket.gif",
        "naïve résumé final v2.docx",
        "Café résumé.pdf",
        "测试结果.png",
        '"evil"\r\n.png',
    ],
)
def test_sanitize_filename_output_is_latin1_safe(raw: str) -> None:
    # Pin the load-bearing property: whatever goes in, the output
    # must be encodable as latin-1 so Starlette's header encoder
    # doesn't crash the request.
    assert _latin1_ok(_sanitize_filename(raw))


@pytest.mark.parametrize("raw", ["", None, ".png", "...", "   "])
def test_sanitize_filename_falls_back_to_evidence(raw: str | None) -> None:
    result = _sanitize_filename(raw)
    # ``evidence`` or ``evidence.ext`` — never the empty string.
    assert result.startswith("evidence")


def test_sanitize_filename_caps_extension_length() -> None:
    # Pathological extension lengths are clipped so a weird upload
    # can't blow out the filesystem path budget.
    result = _sanitize_filename("foo." + "x" * 50)
    stem, dot, ext = result.partition(".")
    assert len(ext) <= 10


def test_sanitize_filename_idempotent() -> None:
    # The download path also runs the sanitiser as defence-in-depth
    # against historical DB rows. A second pass must NOT mangle a
    # value that's already clean.
    once = _sanitize_filename("Screenshot 2026-05-20 at 4.00.01 PM.png")
    twice = _sanitize_filename(once)
    assert once == twice
