"""Presence tracking backed by the database (PresenceSession rows).

A session opens on a person's first detection and remains open while new
detections keep arriving inside `presence_timeout_seconds`; a periodic task
closes expired sessions and emits events.
"""

import asyncio
import datetime
import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import config
from core.database import as_utc, session_scope
from core.events import event_bus
from core.models import AppSettings, Person, PresenceSession

logger = logging.getLogger(__name__)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


async def touch_presence(session: AsyncSession, person_id: int,
                         source: Optional[str] = None) -> None:
    """Open or refresh the active presence session of a person."""
    result = await session.execute(
        select(PresenceSession)
        .where(PresenceSession.person_id == person_id, PresenceSession.ended_at.is_(None))
        .order_by(PresenceSession.started_at.desc())
        .limit(1)
    )
    active = result.scalar_one_or_none()

    now = _now()
    if active is None:
        session.add(PresenceSession(person_id=person_id, source=source,
                                    started_at=now, last_seen_at=now))
        await session.flush()
    else:
        active.last_seen_at = now
        if source:
            active.source = source


async def get_active_sessions() -> List[dict]:
    """List people currently present (open sessions)."""
    async with session_scope() as session:
        result = await session.execute(
            select(PresenceSession, Person)
            .join(Person, Person.id == PresenceSession.person_id)
            .where(PresenceSession.ended_at.is_(None))
            .order_by(PresenceSession.started_at)
        )
        rows = result.all()
        now = _now()
        active = []
        for presence, person in rows:
            started = as_utc(presence.started_at) or now
            last_seen = as_utc(presence.last_seen_at) or now
            active.append({
                "person_id": person.id,
                "name": person.name,
                "display_name": person.display_name,
                "face_image_path": person.face_image_path,
                "source": presence.source,
                "started_at": started.isoformat(),
                "last_seen_at": last_seen.isoformat(),
                "duration_seconds": round((last_seen - started).total_seconds(), 1),
                "seconds_since_last_seen": round((now - last_seen).total_seconds(), 1),
            })
        return active


async def get_timeout_seconds() -> int:
    """Read presence timeout from runtime settings, falling back to env config."""
    try:
        async with session_scope() as session:
            result = await session.execute(select(AppSettings).where(AppSettings.id == 1))
            row = result.scalar_one_or_none()
            if row:
                return max(5, row.presence_timeout_seconds)
    except Exception:
        pass
    return max(5, config.get_settings().PRESENCE_TIMEOUT_SECONDS)


async def close_expired_sessions(timeout_seconds: int) -> List[int]:
    """Close sessions whose last detection is older than the timeout.

    Returns ids of people whose session just ended.
    """
    cutoff = _now() - datetime.timedelta(seconds=timeout_seconds)

    async with session_scope() as session:
        result = await session.execute(
            select(PresenceSession).where(PresenceSession.ended_at.is_(None))
        )
        expired: List[int] = []
        for presence in result.scalars().all():
            last_seen = as_utc(presence.last_seen_at)
            if last_seen is not None and last_seen < cutoff:
                presence.ended_at = _now()
                expired.append(presence.person_id)
        return expired


async def presence_timeout_task(get_timeout) -> None:
    """Background loop closing expired presence sessions and emitting events."""
    logger.info("Task de expiração de presença iniciada.")
    while True:
        try:
            timeout = await get_timeout()
            ended_ids = await close_expired_sessions(timeout)
            for person_id in ended_ids:
                await event_bus.publish_async("presence_ended", {"person_id": person_id})
            if ended_ids:
                logger.debug("%d sessão(ões) de presença encerradas.", len(ended_ids))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Erro no loop de expiração de presença.")
        await asyncio.sleep(10)
