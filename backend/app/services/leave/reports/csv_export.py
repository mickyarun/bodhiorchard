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

"""Report rows as CSV bytes that open cleanly in Excel and can't run formulas.

Text cells starting with ``= + - @`` or a tab/carriage return are prefixed
with ``'`` so a spreadsheet shows them as text rather than evaluating them
(a name like ``=HYPERLINK(...)`` is otherwise live). Numbers and dates are
written as values and never escaped, so a negative adjustment stays a
number. A UTF-8 byte-order mark makes Excel read non-ASCII names correctly.
"""

import csv
import io
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from decimal import Decimal

Cell = str | Decimal | int | date | datetime | None

BOM = "﻿"
_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def _text(value: str) -> str:
    return "'" + value if value.startswith(_FORMULA_STARTS) else value


def _cell(value: Cell) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return _text(value)
    if isinstance(value, datetime):
        return value.isoformat(timespec="minutes")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def to_csv(header: Sequence[str], rows: Iterable[Sequence[Cell]]) -> bytes:
    """``header`` then ``rows`` as UTF-8 CSV with a BOM and CRLF line ends."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow([_text(h) for h in header])
    writer.writerows([_cell(value) for value in row] for row in rows)
    return (BOM + out.getvalue()).encode("utf-8")


def csv_filename(report: str, *parts: date | int) -> str:
    """ASCII-only, from the report name and its dates: never a person's name."""
    return "-".join(["leave", report, *(str(p) for p in parts)]) + ".csv"
