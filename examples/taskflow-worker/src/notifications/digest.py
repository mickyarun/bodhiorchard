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

"""Notification digest — aggregates unread notifications into a summary email.

Runs on a schedule (daily or weekly per user preference) and sends
a single digest email instead of individual notifications.
"""


def build_digest(user_id: int, period: str = "daily") -> dict:
    """Collect unread notifications for a user and format a digest.

    Args:
        user_id: The user to build digest for.
        period: "daily" or "weekly".

    Returns:
        Dict with subject, body, and notification count.
    """
    # In production: query notifications from DB
    return {
        "subject": f"Your {period} TaskFlow digest",
        "body": "You have 5 unread notifications...",
        "count": 5,
    }


def handle_digest_job(payload: dict) -> None:
    """Process a digest notification job."""
    user_id = payload["user_id"]
    period = payload.get("period", "daily")

    digest = build_digest(user_id, period)
    if digest["count"] == 0:
        return  # Nothing to send

    from src.notifications.email_sender import send_email

    send_email(
        to_email=payload["email"],
        subject=digest["subject"],
        body=digest["body"],
    )
