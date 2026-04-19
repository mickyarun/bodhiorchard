"""Task reminder scheduler — checks for upcoming due dates and sends reminders.

Cross-references tasks from taskflow-api and sends notifications
via the notification delivery pipeline.
"""

from datetime import datetime, timedelta, UTC


def find_tasks_due_soon(hours: int = 24) -> list[dict]:
    """Find tasks with due dates within the next N hours.

    In production, queries the tasks table in the shared database.
    """
    cutoff = datetime.now(UTC) + timedelta(hours=hours)
    # db.query(Task).filter(Task.due_date <= cutoff, Task.status != 'done').all()
    return []


def handle_reminder_job(payload: dict) -> None:
    """Check for upcoming tasks and send reminder notifications."""
    hours = payload.get("hours_ahead", 24)
    tasks = find_tasks_due_soon(hours)

    for task in tasks:
        from src.notifications.email_sender import handle_email_job

        handle_email_job({
            "to_email": task["assignee_email"],
            "template": "reminder",
            "subject": f"Task due soon: {task['title']}",
            "context": {
                "task_title": task["title"],
                "due_date": task["due_date"],
            },
        })

    print(f"Processed {len(tasks)} reminder(s)")
