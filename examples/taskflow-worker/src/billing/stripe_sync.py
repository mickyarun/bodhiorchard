"""Stripe synchronization — keeps local billing state in sync with Stripe.

Handles webhook events, subscription status updates, and payment
confirmation from Stripe's API.
"""


def sync_subscription_status(stripe_sub_id: str) -> dict:
    """Fetch subscription status from Stripe and update local DB.

    Returns the synced status.
    """
    # In production: stripe.Subscription.retrieve(stripe_sub_id)
    return {"status": "active", "current_period_end": "2026-01-15"}


def process_payment_webhook(event: dict) -> None:
    """Handle a Stripe payment webhook event.

    Updates invoice status based on payment success/failure.
    """
    event_type = event.get("type", "")

    if event_type == "invoice.paid":
        invoice_id = event["data"]["object"]["id"]
        print(f"Payment confirmed for Stripe invoice {invoice_id}")
        # Update local invoice status to 'paid'

    elif event_type == "invoice.payment_failed":
        invoice_id = event["data"]["object"]["id"]
        print(f"Payment failed for Stripe invoice {invoice_id}")
        # Update local invoice status to 'failed'
        # Send notification to user


def handle_stripe_sync_job(payload: dict) -> None:
    """Sync billing state with Stripe."""
    action = payload.get("action", "sync_subscription")

    if action == "sync_subscription":
        stripe_sub_id = payload["stripe_subscription_id"]
        sync_subscription_status(stripe_sub_id)
    elif action == "process_webhook":
        process_payment_webhook(payload["event"])
