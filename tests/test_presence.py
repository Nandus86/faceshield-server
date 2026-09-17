"""Tests for presence sessions (open, refresh, expire)."""

import asyncio
import datetime

import pytest
from sqlalchemy import select, update


def run(coro):
    return asyncio.run(coro)


async def _person_id_for(name: str) -> int:
    from core.database import session_scope
    from core.models import Person

    async with session_scope() as session:
        person = Person(name=name, embedding=[0.0] * 512)
        session.add(person)
        await session.flush()
        return person.id


class TestPresence:
    def test_touch_opens_and_refreshes_session(self):
        async def scenario():
            from core.presence_service import get_active_sessions, touch_presence
            from core.database import session_scope

            person_id = await _person_id_for("Alice")
            async with session_scope() as session:
                await touch_presence(session, person_id, source="test")
            active = await get_active_sessions()
            assert len(active) == 1
            assert active[0]["person_id"] == person_id

            # Second touch must not create a duplicate session.
            async with session_scope() as session:
                await touch_presence(session, person_id, source="test")
            active = await get_active_sessions()
            assert len(active) == 1

            return person_id

        run(scenario())

    def test_expired_sessions_close(self):
        async def scenario():
            from core.database import session_scope
            from core.models import PresenceSession
            from core.presence_service import (
                close_expired_sessions,
                get_active_sessions,
                touch_presence,
            )

            person_id = await _person_id_for("Bob")
            async with session_scope() as session:
                await touch_presence(session, person_id)

            # Nothing expired yet (just touched).
            assert await close_expired_sessions(timeout_seconds=60) == []

            # Backdate last_seen beyond any reasonable timeout.
            old = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=10)
            async with session_scope() as session:
                await session.execute(
                    update(PresenceSession)
                    .where(PresenceSession.person_id == person_id)
                    .values(last_seen_at=old.replace(tzinfo=None))
                )

            ended = await close_expired_sessions(timeout_seconds=30)
            assert ended == [person_id]

            active = await get_active_sessions()
            assert len(active) == 0

        run(scenario())
