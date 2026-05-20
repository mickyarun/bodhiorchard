# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""``_content_disposition`` must be latin-1 clean for any user filename.

Production crash that prompted this helper:

    UnicodeEncodeError: 'latin-1' codec can't encode character '\\u202f'

A QA user uploaded a macOS screenshot whose filename contained a narrow
no-break space (U+202F — common in OS-formatted timestamps like
"Screenshot 2026-05-20 at 11.44 AM.png"). The download endpoint
returned a 500 because Starlette rejected the non-latin-1 char when
encoding the ``Content-Disposition`` header.

These tests pin RFC 6266 compliance:
* The full header value is latin-1 encodable.
* Modern clients see the original filename via ``filename*=UTF-8''…``.
* Legacy clients see an ASCII-only fallback via ``filename="…"``.
* Header-injection chars (``"``, CR, LF) are still neutralised.
"""

from __future__ import annotations

import pytest

from app.api.v1.bud_qa import _content_disposition


def _latin1_ok(value: str) -> bool:
    try:
        value.encode("latin-1")
    except UnicodeEncodeError:
        return False
    return True


@pytest.mark.parametrize(
    "filename",
    [
        "Screenshot 2026-05-20 at 11.44 AM.png",  # narrow no-break space
        "café.pdf",
        "测试结果.png",  # CJK
        "🚀.gif",
        "naïve résumé final v2.docx",
        "plain-ascii.txt",
    ],
)
def test_header_is_latin1_encodable(filename: str) -> None:
    header = _content_disposition(filename)
    assert _latin1_ok(header), f"header not latin-1 clean for {filename!r}: {header!r}"


def test_modern_clients_see_full_filename_percent_encoded() -> None:
    # ``filename*=UTF-8''…`` is what every browser since IE 11 uses
    # when both parameters are present. The percent-encoded value must
    # round-trip back to the original Unicode bytes.
    from urllib.parse import unquote

    name = "Screenshot 2026-05-20 at 11.44 AM.png"
    header = _content_disposition(name)
    # Extract the filename* segment.
    fnstar = header.split("filename*=UTF-8''", 1)[1]
    assert unquote(fnstar) == name


def test_legacy_filename_param_is_ascii_only() -> None:
    name = "café résumé.pdf"
    header = _content_disposition(name)
    # The legacy ``filename="…"`` parameter must be ASCII-only so old
    # clients can read it without their own decoder choking.
    legacy = header.split('filename="', 1)[1].split('"', 1)[0]
    legacy.encode("ascii")  # raises if non-ASCII leaked through


def test_header_injection_chars_neutralised_in_legacy_param() -> None:
    name = 'evil"\r\nX-Injected: yes\r\nfinal.png'
    header = _content_disposition(name)
    legacy = header.split('filename="', 1)[1].split('"', 1)[0]
    assert '"' not in legacy
    assert "\r" not in legacy
    assert "\n" not in legacy


def test_emoji_filename_does_not_crash() -> None:
    # Pin the original crash scenario at the helper level too: any 4-byte
    # UTF-8 codepoint must produce a latin-1-safe header.
    header = _content_disposition("🚀 rocket.gif")
    assert _latin1_ok(header)
    assert "filename*=UTF-8''" in header


def test_empty_or_none_filename_falls_back_to_default() -> None:
    # An unexpectedly-null filename (column nullability change, legacy row)
    # must not crash with ``AttributeError`` inside the helper. We default
    # to a sensible ASCII name instead.
    for value in ("", None):
        header = _content_disposition(value)  # type: ignore[arg-type]
        assert _latin1_ok(header)
        assert 'filename="evidence"' in header


def test_legacy_filename_does_not_contain_question_marks() -> None:
    # ``encode("ascii", "replace")`` substitutes ``?`` for each non-ASCII
    # char — but ``?`` is a glob char in many shells and an invalid char
    # on Windows. Modern clients use ``filename*=`` regardless; this
    # pins that legacy clients also get a usable name.
    header = _content_disposition("Screenshot 2026‑05‑20 at 11.44.png")
    legacy = header.split('filename="', 1)[1].split('"', 1)[0]
    assert "?" not in legacy, f"`?` leaked into legacy filename: {legacy!r}"
