"""Bug threshold gate for the testing phase.

When open bugs on a BUD in testing reach the org-configured threshold,
the BUD is auto-rejected back to development. The QA assignee is freed
and the developer is re-assigned to fix the bugs.

Mirrors the auto-transition pattern in ``pr_auto_transition.py``
(all-repos-merged → advance) but in reverse (too-many-bugs → retreat).
"""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.repositories.bug import BugRepository
from app.services.bud_timeline import record_event
from app.services.event_bus import publish
from app.services.org_settings import get_bug_reject_threshold

logger = structlog.get_logger(__name__)


async def check_bug_threshold(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
) -> bool:
    """Check if open bugs exceed the threshold; if so, reject to development.

    Only fires when ``bud.status == TESTING``. Returns ``True`` if the
    BUD was rejected, ``False`` otherwise.

    Side-effects on rejection:
    - Sets ``bud.status = DEVELOPMENT``
    - Records ``testing_rejected`` timeline event
    - Records ``status_change`` timeline event (auto=True)
    - Unassigns the current QA tester
    - Auto-assigns a developer for the development phase
    - Publishes SSE event for live UI refresh
    """
    if bud.status != BUDStatus.TESTING:
        return False

    # Fetch org config for threshold
    from app.models.organization import Organization

    org = await db.get(Organization, org_id)
    if org is None:
        return False

    threshold = get_bug_reject_threshold(org.config)

    bug_repo = BugRepository(db, org_id=org_id)
    open_count = await bug_repo.count_open_for_bud(bud.id)

    if open_count < threshold:
        return False

    # Threshold exceeded — reject back to development
    old_assignee_id = bud.assignee_id
    bud.status = BUDStatus.DEVELOPMENT

    await record_event(
        db,
        org_id,
        bud.id,
        "testing_rejected",
        detail={
            "bug_count": open_count,
            "threshold": threshold,
            "from": "testing",
            "to": "development",
            "previous_assignee_id": str(old_assignee_id) if old_assignee_id else None,
        },
    )
    await record_event(
        db,
        org_id,
        bud.id,
        "status_change",
        detail={
            "from": "testing",
            "to": "development",
            "auto": True,
            "reason": f"Open bugs ({open_count}) exceeded threshold ({threshold})",
        },
    )

    # Free the QA assignee and re-assign a developer
    from app.services.bud_assignment import auto_assign_for_phase, unassign_bud

    if old_assignee_id:
        await unassign_bud(db, org_id, bud)

    await auto_assign_for_phase(db, org_id, bud, BUDStatus.DEVELOPMENT)

    publish(
        f"bud:{bud.id}:activity",
        {
            "event_type": "testing_rejected",
            "bug_count": open_count,
            "threshold": threshold,
        },
    )

    logger.info(
        "bud_testing_rejected",
        bud_id=str(bud.id),
        bud_number=bud.bud_number,
        open_bugs=open_count,
        threshold=threshold,
    )
    return True
