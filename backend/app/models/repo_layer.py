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

"""``RepoLayer`` enum used by ``tracked_repositories.repo_layer``.

Lives in its own module so the classifier service in
:mod:`app.services.scan.repo_classify` can import it without pulling in
the SQLAlchemy model graph (which would be circular at scan-runtime).

Six layers cover the architectures we have today:

* ``FRONTEND``  — UI app (Vue, React, Nuxt, mobile shell, etc.)
* ``BACKEND``   — request/response API server (FastAPI, NestJS, Express, …)
* ``PROCESSOR`` — long-running consumer / queue worker (Kafka, BullMQ, …)
* ``BATCH``     — cron / scheduler / one-shot job
* ``DB``        — schema-only repo (Liquibase, Atlas, raw SQL migrations)
* ``SHARED``    — library / SDK / proto package shared by other repos

The classifier defaults to ``SHARED`` when neither the manifest nor the
name pattern produces a strong signal — better to under-classify than to
miscategorise a real backend as a frontend.
"""

from enum import StrEnum


class RepoLayer(StrEnum):
    """Architectural role a tracked repository plays in the org."""

    FRONTEND = "frontend"
    BACKEND = "backend"
    PROCESSOR = "processor"
    BATCH = "batch"
    DB = "db"
    SHARED = "shared"
