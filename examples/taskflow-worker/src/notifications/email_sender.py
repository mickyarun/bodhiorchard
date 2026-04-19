"""Email notification delivery via SendGrid.

Processes email jobs from the queue, renders templates,
and sends via the SendGrid API.
"""

from jinja2 import Environment, DictLoader

# Simple email templates
TEMPLATES = {
    "task_assigned": "You've been assigned to: {{ task_title }}",
    "task_comment": "New comment on {{ task_title }}: {{ comment_preview }}",
    "invoice_ready": "Your invoice #{{ invoice_id }} for ${{ amount }} is ready.",
    "reminder": "Reminder: {{ task_title }} is due {{ due_date }}",
    "password_reset": "Click here to reset your password: {{ reset_link }}",
}

_env = Environment(loader=DictLoader(TEMPLATES))


def render_email(template_name: str, context: dict) -> str:
    """Render an email body from a template."""
    template = _env.get_template(template_name)
    return template.render(**context)


def send_email(to_email: str, subject: str, body: str) -> bool:
    """Send an email via SendGrid API.

    Returns True if the email was accepted for delivery.
    """
    # In production: use sendgrid.SendGridAPIClient
    print(f"Sending email to {to_email}: {subject}")
    return True


def handle_email_job(payload: dict) -> None:
    """Process an email notification job from the queue."""
    to_email = payload["to_email"]
    template = payload["template"]
    context = payload.get("context", {})

    body = render_email(template, context)
    subject = f"TaskFlow: {payload.get('subject', 'Notification')}"

    success = send_email(to_email, subject, body)
    if not success:
        raise RuntimeError(f"Failed to send email to {to_email}")
