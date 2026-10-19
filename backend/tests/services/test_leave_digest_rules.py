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

"""The daily post's timing and text, and the Slack approval layouts."""

import hashlib
import hmac
import time
import uuid
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.models.leave_request import HalfDay
from app.services.leave.digest_compose import OutToday, compose
from app.services.leave.digest_schedule import due_local_date
from app.services.leave.slack_blocks import approval_blocks, escape
from app.services.slack_verify import verify_slack_signature

KOLKATA = ZoneInfo("Asia/Kolkata")
MON = date(2026, 10, 19)


def test_post_is_due_from_post_time_for_three_hours() -> None:
    # 09:30 IST is 04:00 UTC.
    assert due_local_date(datetime(2026, 10, 19, 3, 59, tzinfo=UTC), KOLKATA, "09:30") is None
    assert due_local_date(datetime(2026, 10, 19, 4, 0, tzinfo=UTC), KOLKATA, "09:30") == MON
    assert due_local_date(datetime(2026, 10, 19, 6, 59, tzinfo=UTC), KOLKATA, "09:30") == MON
    assert due_local_date(datetime(2026, 10, 19, 7, 0, tzinfo=UTC), KOLKATA, "09:30") is None


def _out(name: str, back: date | None = None, half: HalfDay = HalfDay.NONE) -> OutToday:
    return OutToday(name=name, half_day=half, back_on=back)


def test_compose_lists_people_with_when_they_are_back() -> None:
    text = compose(
        MON,
        away=[
            _out("Zara", date(2026, 10, 22)),
            _out("asha", date(2026, 10, 20)),
            _out("Bala", half=HalfDay.SECOND_HALF),
            _out("Chen", date(2026, 11, 3)),
        ],
        remote=[_out("Dev"), _out("Eli", half=HalfDay.FIRST_HALF)],
        holidays=["UK – London (Summer bank holiday)"],
    )
    assert text == (
        "*Who's out today, Mon 19 Oct*\n"
        "On leave: asha (back tomorrow), Bala (out this afternoon), "
        "Chen (back 3 Nov), Zara (back Thu)\n"
        "Working from home: Dev, Eli (morning)\n"
        "Holiday: UK – London (Summer bank holiday)"
    )


def test_names_in_the_channel_post_are_escaped() -> None:
    text = compose(MON, away=[_out("<!channel>")], remote=[], holidays=["<https://x|Pay>"])
    assert text is not None
    assert "<!channel>" not in text and "&lt;!channel&gt;" in text
    assert "&lt;https://x|Pay&gt;" in text


def test_nothing_to_post_when_everyone_is_in() -> None:
    assert compose(MON, [], [], []) is None


def test_names_cannot_inject_slack_markup() -> None:
    assert escape("<!channel> & co") == "&lt;!channel&gt; &amp; co"
    blocks = approval_blocks("<@U1> requested leave", uuid.uuid4(), "https://app/leave")
    assert blocks[0]["text"]["text"] == "&lt;@U1&gt; requested leave"
    assert [e["action_id"] for e in blocks[1]["elements"]] == [
        "leave_approve",
        "leave_reject",
        "leave_open",
    ]


def _sign(secret: str, ts: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), f"v0:{ts}:{body.decode()}".encode(), hashlib.sha256)
    return "v0=" + digest.hexdigest()


def test_slack_signature_must_match_and_be_recent() -> None:
    body = b"payload=%7B%7D"
    now = str(int(time.time()))
    assert verify_slack_signature("s3cret", now, body, _sign("s3cret", now, body)) == (True, "")
    assert not verify_slack_signature("s3cret", now, body, _sign("other", now, body))[0]
    old = str(int(time.time()) - 600)
    assert not verify_slack_signature("s3cret", old, body, _sign("s3cret", old, body))[0]
    assert verify_slack_signature("s3cret", "nope", body, "v0=x") == (False, "bad_timestamp")
    reason = verify_slack_signature("s3cret", now, body, "v0=bad")[1]
    assert "s3cr" not in reason
