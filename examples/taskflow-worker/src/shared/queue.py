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
