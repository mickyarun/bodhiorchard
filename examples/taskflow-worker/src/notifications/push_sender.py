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
