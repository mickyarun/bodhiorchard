# TaskFlow Worker

Background job processor for TaskFlow. Consumes jobs from Redis and handles email delivery, push notifications, reminders, and billing.

## Setup

```bash
cd examples/taskflow-worker
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python -m src.main
```

Requires Redis on `localhost:6379` (optional for development — worker exits gracefully without it).

## Modules

- `/auth` — Session cleanup, inactive user detection
- `/notifications` — Email (SendGrid), push (FCM), daily/weekly digest
- `/reminders` — Scheduled task due-date checks
- `/billing` — Invoice generation, Stripe subscription sync

## Architecture

The worker shares a database with `taskflow-api`. Jobs are queued via Redis:

```
taskflow-api  →  Redis queue  →  taskflow-worker
(enqueue)        "taskflow:jobs"   (consume + process)
```

Job types: `send_email`, `send_push`, `send_digest`, `check_reminders`, `generate_invoice`, `sync_stripe`, `cleanup_sessions`
