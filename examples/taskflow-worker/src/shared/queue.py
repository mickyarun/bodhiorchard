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

"""Redis-backed job queue consumer."""

import json
from typing import Generator


def get_redis_client():
    """Get a Redis connection (stubbed for development)."""
    return None  # In production: redis.Redis(host="localhost", port=6379, db=0)


def consume_jobs() -> Generator[dict, None, None]:
    """Consume jobs from the Redis queue.

    In development, yields sample jobs for testing.
    In production, this blocks on BRPOP.
    """
    client = get_redis_client()
    if client is None:
        return

    while True:
        _, raw = client.brpop("taskflow:jobs", timeout=5)
        if raw:
            yield json.loads(raw)


def enqueue_job(job_type: str, payload: dict) -> None:
    """Push a job onto the Redis queue."""
    client = get_redis_client()
    if client:
        client.lpush("taskflow:jobs", json.dumps({"type": job_type, "payload": payload}))
