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

"""Async SQLAlchemy 2.0 database engine and session management."""

from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

engine = create_async_engine(
    settings.db.database_url,
    echo=False,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=1800,  # Recycle connections every 30 min (avoids stale TCP after PG restart)
    pool_timeout=30,  # Fail fast if no connection available within 30s (default is 30 already)
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def _request_session() -> AsyncGenerator[AsyncSession, None]:
    """Open a session, commit it if the route succeeds, roll it back if not."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db(
    session: AsyncSession = Depends(_request_session, scope="function"),
) -> AsyncSession:
    """FastAPI dependency for the request's database session.

    The commit must land before the client sees the response, or a client
    that reads straight after a write can miss it, and a failed commit is
    reported as success. A plain ``yield`` dependency no longer guarantees
    that: since FastAPI 0.118 its exit code runs after the response is sent.
    ``scope="function"`` (FastAPI 0.121+) runs the commit as soon as the
    route returns, before the response goes out.

    The session lives in ``_request_session`` so every ``Depends(get_db)``
    gets the function scope without having to ask for it.
    """
    return session
