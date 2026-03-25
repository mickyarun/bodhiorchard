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
from app.services.job_agents import (
    handle_code_review_job,
    handle_prd_job,
    handle_tech_arch_job,
    handle_triage_job,
)
from app.services.job_chat import handle_chat_job
from app.services.job_design import handle_design_agent_job, handle_design_extract_job
from app.services.job_queue import (
    JOB_BUD_AGENT,
    JOB_BUD_CHAT,
    JOB_CODE_REVIEW,
    JOB_DESIGN_AGENT,
    JOB_DESIGN_EXTRACT,
    JOB_PRD_AGENT,
    JOB_TECH_ARCH,
    JOB_TRIAGE,
    register_job_type,
)

# Re-export all handlers so existing imports continue to work
__all__ = [
    "setup_job_handlers",
    "handle_bud_agent_job",
    "handle_chat_job",
    "handle_triage_job",
    "handle_prd_job",
    "handle_design_agent_job",
    "handle_design_extract_job",
    "handle_tech_arch_job",
    "handle_code_review_job",
]


def setup_job_handlers() -> None:
    """Register all job types with the queue system.

    Called once from app lifespan before start_workers().
    To add a new job type, add a register_job_type() call here.
    """
    chat_workers = int(os.environ.get("JOB_CHAT_WORKERS", "2"))

    register_job_type(JOB_BUD_CHAT, handle_chat_job, worker_count=chat_workers)
    register_job_type(JOB_TRIAGE, handle_triage_job, worker_count=1)
    register_job_type(JOB_PRD_AGENT, handle_prd_job, worker_count=1)
    register_job_type(JOB_DESIGN_AGENT, handle_design_agent_job, worker_count=2)
    register_job_type(JOB_DESIGN_EXTRACT, handle_design_extract_job, worker_count=1)
    register_job_type(JOB_TECH_ARCH, handle_tech_arch_job, worker_count=1)
    register_job_type(JOB_CODE_REVIEW, handle_code_review_job, worker_count=1)

    # Unified BUD agent handler (new path — replaces PRD/tech_arch/code_review above)
    bud_agent_workers = int(os.environ.get("JOB_BUD_AGENT_WORKERS", "2"))
    register_job_type(JOB_BUD_AGENT, handle_bud_agent_job, worker_count=bud_agent_workers)
