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

"""TaskFlow Worker — background job processor.

Consumes jobs from Redis queues and processes them:
- Email/push notification delivery
- Scheduled task reminders
- Invoice generation and Stripe sync
- Session cleanup
"""

import time

from src.shared.queue import consume_jobs
from src.notifications.email_sender import handle_email_job
from src.notifications.push_sender import handle_push_job
from src.notifications.digest import handle_digest_job
from src.reminders.scheduler import handle_reminder_job
from src.billing.invoice_generator import handle_invoice_job
from src.billing.stripe_sync import handle_stripe_sync_job
from src.auth.session_cleanup import handle_session_cleanup_job

JOB_HANDLERS = {
    "send_email": handle_email_job,
    "send_push": handle_push_job,
    "send_digest": handle_digest_job,
    "check_reminders": handle_reminder_job,
    "generate_invoice": handle_invoice_job,
    "sync_stripe": handle_stripe_sync_job,
    "cleanup_sessions": handle_session_cleanup_job,
}


def run_worker():
    """Main worker loop — consume and dispatch jobs."""
    print("TaskFlow Worker starting...")
    for job in consume_jobs():
        handler = JOB_HANDLERS.get(job["type"])
        if handler:
            try:
                handler(job["payload"])
            except Exception as e:
                print(f"Job {job['type']} failed: {e}")
        else:
            print(f"Unknown job type: {job['type']}")
        time.sleep(0.1)


if __name__ == "__main__":
    run_worker()
