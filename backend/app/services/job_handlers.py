# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

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
    JOB_TRIAGE,
    register_job_type,
)

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


def setup_job_handlers() -> None:
    """Register all job types with the queue system.

    Called once from app lifespan before start_workers().
    To add a new job type, add a register_job_type() call here.
    """
    chat_workers = int(os.environ.get("JOB_CHAT_WORKERS", "2"))

    register_job_type(JOB_BUD_CHAT, handle_chat_job, worker_count=chat_workers)
    register_job_type(JOB_TRIAGE, handle_triage_job, worker_count=1)
    register_job_type(JOB_DESIGN_AGENT, handle_design_agent_job, worker_count=2)
    register_job_type(JOB_DESIGN_EXTRACT, handle_design_extract_job, worker_count=1)

    # Unified BUD agent handler (PRD, tech arch, code review, testing)
    bud_agent_workers = int(os.environ.get("JOB_BUD_AGENT_WORKERS", "2"))
    register_job_type(JOB_BUD_AGENT, handle_bud_agent_job, worker_count=bud_agent_workers)

    # Jira import pipeline
    register_job_type(JOB_JIRA_DISCOVERY, handle_discovery_job, worker_count=1)
    register_job_type(JOB_JIRA_IMPORT, handle_import_job, worker_count=1)
    register_job_type(JOB_JIRA_ENRICH, handle_enrich_job, worker_count=1)
