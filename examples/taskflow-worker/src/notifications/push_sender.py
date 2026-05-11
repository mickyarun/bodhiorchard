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

"""Push notification delivery (FCM / APNs).

Sends push notifications to mobile devices registered
in the user's notification preferences.
"""


def send_push_notification(device_token: str, title: str, body: str) -> bool:
    """Send a push notification to a device."""
    # In production: use firebase_admin or APNs client
    print(f"Push to {device_token[:8]}...: {title}")
    return True


def handle_push_job(payload: dict) -> None:
    """Process a push notification job from the queue."""
    device_tokens = payload.get("device_tokens", [])
    title = payload["title"]
    body = payload.get("body", "")

    for token in device_tokens:
        send_push_notification(token, title, body)
