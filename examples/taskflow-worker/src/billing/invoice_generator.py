"""Invoice generation — calculates charges and creates invoice records.

Runs at the end of each billing cycle to generate invoices
based on plan pricing and usage overages.
"""


def calculate_charges(user_id: int) -> dict:
    """Calculate the total charges for a user's billing period.

    Combines base plan price with any usage overages.
    """
    # In production: query subscription + usage_records
    return {
        "base_price": 29.00,
        "overage": 0.00,
        "total": 29.00,
        "currency": "usd",
    }


def create_invoice(user_id: int, charges: dict) -> int:
    """Create an invoice record in the database.

    Returns the invoice ID.
    """
    # In production: INSERT into invoices table
    print(f"Invoice created for user {user_id}: ${charges['total']}")
    return 1


def handle_invoice_job(payload: dict) -> None:
    """Generate an invoice for a user."""
    user_id = payload["user_id"]
    charges = calculate_charges(user_id)

    if charges["total"] <= 0:
        return  # Free plan, no invoice

    invoice_id = create_invoice(user_id, charges)

    # Notify user that invoice is ready
    from src.notifications.email_sender import handle_email_job

    handle_email_job({
        "to_email": payload["email"],
        "template": "invoice_ready",
        "subject": "Your TaskFlow invoice is ready",
        "context": {
            "invoice_id": invoice_id,
            "amount": charges["total"],
        },
    })
