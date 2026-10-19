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

"""When the daily who's-out post is due (pure, no I/O).

Due from the org's post time until a few hours after it, in the org's
timezone. A late restart still posts within that window, but never posts
the morning message at night.
"""

from datetime import date, datetime, time, timedelta, tzinfo

LATEST_AFTER = timedelta(hours=3)


def due_local_date(now_utc: datetime, zone: tzinfo, post_time: str) -> date | None:
    """The local date whose post is due now, or None outside the window."""
    local = now_utc.astimezone(zone)
    hour, minute = (int(part) for part in post_time.split(":"))
    start = datetime.combine(local.date(), time(hour, minute), tzinfo=zone)
    return local.date() if start <= local < start + LATEST_AFTER else None
