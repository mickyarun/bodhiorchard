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

"""Background job: clean up expired refresh tokens and sessions.

Runs on a schedule (daily) to remove stale auth data and
revoked tokens older than 30 days.
"""

from datetime import datetime, timedelta, UTC


def handle_session_cleanup_job(payload: dict) -> None:
    """Remove expired refresh tokens from the database.

    This cross-references the auth module in taskflow-api — tokens
    are created there but cleaned up here to avoid blocking API requests.
    """
    cutoff = datetime.now(UTC) - timedelta(days=30)
    # In production: db.query(RefreshToken).filter(
    #     or_(RefreshToken.expires_at < cutoff, RefreshToken.revoked == True)
    # ).delete()
    print(f"Cleaned up sessions older than {cutoff.isoformat()}")


def cleanup_inactive_users(days_inactive: int = 90) -> int:
    """Flag users who haven't logged in for N days.

    Sends a re-engagement notification before deactivation.
    """
    # In production: query users by last_login_at
    print(f"Checking for users inactive for {days_inactive} days")
    return 0
