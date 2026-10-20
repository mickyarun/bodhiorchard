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

"""Splitting a request's days at a report's date range, and CSV export."""

import csv
import io
from datetime import date
from decimal import Decimal

from app.services.leave.reports.attribution import InRange, Span, within
from app.services.leave.reports.csv_export import BOM, csv_filename, to_csv

MON_FRI = [0, 1, 2, 3, 4]
D = Decimal


def split(span: Span, start: date, end: date, holidays: dict[date, str] | None = None) -> InRange:
    return within(span, start, end, working_days=MON_FRI, holidays=holidays or {})


def test_a_request_inside_the_range_keeps_its_stored_days() -> None:
    # Stored 3 days even though today's calendar might say otherwise.
    span = Span(date(2026, 6, 8), date(2026, 6, 10), D("3"), D("1"))
    assert split(span, date(2026, 6, 1), date(2026, 6, 30)) == InRange(D("3"), D("1"))


def test_no_overlap_counts_nothing() -> None:
    span = Span(date(2026, 5, 4), date(2026, 5, 5), D("2"), D("0"))
    assert split(span, date(2026, 6, 1), date(2026, 6, 30)) == InRange(D("0"), D("0"))


def test_a_request_across_a_month_end_is_split_by_working_days() -> None:
    # Thu 28 May - Wed 3 Jun 2026: 28, 29 May | 1, 2, 3 Jun (weekend skipped).
    span = Span(date(2026, 5, 28), date(2026, 6, 3), D("5"), D("0"))
    assert split(span, date(2026, 5, 1), date(2026, 5, 31)).days == D("2")
    assert split(span, date(2026, 6, 1), date(2026, 6, 30)).days == D("3")


def test_loss_of_pay_is_the_tail_of_the_request() -> None:
    span = Span(date(2026, 5, 28), date(2026, 6, 3), D("5"), D("2"))
    may = split(span, date(2026, 5, 1), date(2026, 5, 31))
    june = split(span, date(2026, 6, 1), date(2026, 6, 30))
    assert (may.lop_days, june.lop_days) == (D("0"), D("2"))
    big = Span(date(2026, 5, 28), date(2026, 6, 3), D("5"), D("4"))
    assert split(big, date(2026, 5, 1), date(2026, 5, 31)).lop_days == D("1")


def test_holidays_and_drift_never_push_days_past_the_stored_total() -> None:
    # Booked before 1 Jun became a holiday: stored 5 days, today's count says 4.
    span = Span(date(2026, 5, 28), date(2026, 6, 3), D("5"), D("0"))
    holiday = {date(2026, 6, 1): "New holiday"}
    may = split(span, date(2026, 5, 1), date(2026, 5, 31), holiday)
    june = split(span, date(2026, 6, 1), date(2026, 6, 30), holiday)
    assert may.days == D("2") and june.days <= D("3")
    # A range in the middle of the request still adds up.
    mid = split(span, date(2026, 5, 29), date(2026, 6, 2), holiday)
    assert mid.days == D("2")


def rows(content: bytes) -> list[list[str]]:
    text = content.decode("utf-8")
    assert text.startswith(BOM)
    return list(csv.reader(io.StringIO(text[len(BOM) :])))


def test_csv_escapes_formula_text_but_not_numbers_or_dates() -> None:
    out = to_csv(
        ["Name", "Days", "From"],
        [["=HYPERLINK(1)", D("-2.0"), date(2026, 6, 1)], ["@sum", D("1.5"), None]],
    )
    assert rows(out) == [
        ["Name", "Days", "From"],
        ["'=HYPERLINK(1)", "-2.0", "2026-06-01"],
        ["'@sum", "1.5", ""],
    ]
    assert b"\r\n" in out


def test_csv_keeps_non_ascii_names() -> None:
    assert rows(to_csv(["Name"], [["Priya Rāman"]]))[1] == ["Priya Rāman"]


def test_filenames_are_ascii_and_name_no_one() -> None:
    assert csv_filename("summary", date(2026, 6, 1), date(2026, 6, 30)) == (
        "leave-summary-2026-06-01-2026-06-30.csv"
    )
    assert csv_filename("balances", 2026) == "leave-balances-2026.csv"
