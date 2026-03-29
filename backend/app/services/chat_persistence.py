"""Persistence layer for BUD chat — message storage, content updates, design saves.

Extracted from job_chat.py for modularity. Also imported by job_design.py.
"""

import uuid as uuid_mod

import structlog

logger = structlog.get_logger(__name__)


async def persist_chat_message(
    bud_id: str,
    org_id: str,
    section: str,
    role: str,
    message: str,
    design_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
) -> None:
    """Save a chat message to the bud_chat_messages table."""
    from app.database import AsyncSessionLocal
    from app.repositories.bud import BUDChatMessageRepository

    async with AsyncSessionLocal() as db:
        chat_repo = BUDChatMessageRepository(db, org_id=uuid_mod.UUID(org_id))
        await chat_repo.add_message(
            bud_id=uuid_mod.UUID(bud_id),
            section=section,
            role=role,
            message=message,
            design_id=uuid_mod.UUID(design_id) if design_id else None,
            user_id=uuid_mod.UUID(user_id) if user_id else None,
            session_id=uuid_mod.UUID(session_id) if session_id else None,
        )
        await db.commit()


async def persist_chat_update(
    bud_id: str,
    org_id: str,
    section: str,
    content: str,
) -> None:
    """Write updated chat content to the BUD in the database."""
    from app.database import AsyncSessionLocal
    from app.repositories.bud import BUDRepository

    async with AsyncSessionLocal() as db:
        bud_repo = BUDRepository(db, org_id=uuid_mod.UUID(org_id))
        bud = await bud_repo.get_by_id(uuid_mod.UUID(bud_id))
        if bud is not None:
            setattr(bud, section, content)
            await db.commit()
            logger.info("chat_content_persisted", bud_id=bud_id, section=section)


async def persist_design(
    design_id: str,
    org_id: str,
    html: str,
    design_path: str | None = None,
) -> None:
    """Write sanitized wireframe HTML to bud_designs row."""
    from app.database import AsyncSessionLocal
    from app.models.bud import BUDDesignStatus
    from app.repositories.bud import BUDDesignRepository
    from app.services.html_sanitizer import sanitize_design_html

    safe_html = sanitize_design_html(html)

    async with AsyncSessionLocal() as db:
        repo = BUDDesignRepository(db, org_id=uuid_mod.UUID(org_id))
        design = await repo.get_by_id(uuid_mod.UUID(design_id))
        if design is not None:
            design.design_html = safe_html
            design.design_path = design_path
            design.status = BUDDesignStatus.READY
            await db.commit()
            logger.info("design_persisted", design_id=design_id)
