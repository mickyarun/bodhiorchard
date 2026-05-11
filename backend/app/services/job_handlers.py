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

"""Job handlers for the async queue system.

Re-export shim: registers all job types and re-exports handler functions
from their respective modules (job_chat, job_design, job_agents).

Each handler receives a job_id and payload dict, performs the work,
and calls update_job() to report progress. Handlers run in worker
tasks and must not raise — they should catch errors and call
update_job(state=FAILED) instead.
"""

import os

from app.services.bud_agent_handler import handle_bud_agent_job
from app.services.jira_enrich import handle_enrich_job
from app.services.jira_import_pipeline import handle_discovery_job, handle_import_job
from app.services.job_agents import handle_triage_job
from app.services.job_chat import handle_chat_job
from app.services.job_design import handle_design_agent_job, handle_design_extract_job
from app.services.job_queue import (
    JOB_BUD_AGENT,
    JOB_BUD_CHAT,
    JOB_DESIGN_AGENT,
    JOB_DESIGN_EXTRACT,
    JOB_JIRA_DISCOVERY,
    JOB_JIRA_ENRICH,
    JOB_JIRA_IMPORT,
    JOB_PR_MERGE_UPDATE,
    JOB_REPO_BULK_ONBOARD,
    JOB_TRIAGE,
    register_job_type,
)
from app.services.job_repo_bulk_clone import handle_bulk_onboard_job
from app.services.scan.pr_merge_update import handle_pr_merge_update

# Re-export all handlers so existing imports continue to work
__all__ = [
    "setup_job_handlers",
    "handle_bud_agent_job",
    "handle_chat_job",
    "handle_triage_job",
    "handle_design_agent_job",
    "handle_design_extract_job",
    "handle_discovery_job",
    "handle_import_job",
]


def _design_extract_default_workers() -> int:
    """Default JOB_DESIGN_EXTRACT worker count.

    Each Claude CLI subprocess is ~600MB resident, so we serialize by
    default. Operators can raise concurrency on beefy boxes via
    ``JOB_DESIGN_EXTRACT_WORKERS``.
    """
    return 1


def setup_job_handlers() -> None:
    """Register all job types with the queue system.

    Called once from app lifespan before start_workers().
    To add a new job type, add a register_job_type() call here.
    """
    chat_workers = int(os.environ.get("JOB_CHAT_WORKERS", "2"))

    register_job_type(JOB_BUD_CHAT, handle_chat_job, worker_count=chat_workers)
    register_job_type(JOB_TRIAGE, handle_triage_job, worker_count=1)
    register_job_type(JOB_DESIGN_AGENT, handle_design_agent_job, worker_count=2)
    # Design-extract spawns ~600MB Claude CLI subprocesses; cap workers
    # on small-RAM hosts via cpu_count proxy + ``JOB_DESIGN_EXTRACT_WORKERS``
    # env override.
    design_extract_workers = int(
        os.environ.get("JOB_DESIGN_EXTRACT_WORKERS", _design_extract_default_workers())
    )
    register_job_type(
        JOB_DESIGN_EXTRACT, handle_design_extract_job, worker_count=design_extract_workers
    )

    # Unified BUD agent handler (PRD, tech arch, code review, testing)
    bud_agent_workers = int(os.environ.get("JOB_BUD_AGENT_WORKERS", "2"))
    register_job_type(JOB_BUD_AGENT, handle_bud_agent_job, worker_count=bud_agent_workers)

    # Jira import pipeline
    register_job_type(JOB_JIRA_DISCOVERY, handle_discovery_job, worker_count=1)
    register_job_type(JOB_JIRA_IMPORT, handle_import_job, worker_count=1)
    register_job_type(JOB_JIRA_ENRICH, handle_enrich_job, worker_count=1)

    # PR-merge feature reconcile (GitHub webhook trigger)
    register_job_type(JOB_PR_MERGE_UPDATE, handle_pr_merge_update, worker_count=2)

    # Bulk GitHub-App repo onboard (Settings → Code "Bulk import" tab)
    register_job_type(JOB_REPO_BULK_ONBOARD, handle_bulk_onboard_job, worker_count=1)
