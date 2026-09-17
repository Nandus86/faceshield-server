"""Unit tests for Event Service and Event Presence."""

import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from core.database import session_scope
from core.event_service import (
    create_event,
    end_event,
    generate_event_csv,
    get_active_event,
    get_event_presence,
    list_events,
    record_event_presence,
)
from core.models import Event, EventPresence, Person
from core.schemas import EventCreate


def run(coro):
    return asyncio.run(coro)


class TestEventService:
    def test_create_and_get_active_event(self):
        async def scenario():
            active_before = await get_active_event()
            assert active_before is None

            created = await create_event(EventCreate(name="Conferência Tech 2026", duration_minutes=120))
            assert created.id is not None
            assert created.name == "Conferência Tech 2026"
            assert created.is_active is True

            active_now = await get_active_event()
            assert active_now is not None
            assert active_now.id == created.id
            assert active_now.name == "Conferência Tech 2026"

            events = await list_events()
            assert len(events) >= 1

        run(scenario())

    def test_end_event(self):
        async def scenario():
            event = await create_event(EventCreate(name="Workshop IA"))
            assert event.is_active is True

            ended = await end_event(event.id)
            assert ended is not None
            assert ended.ended_at is not None
            assert ended.is_active is False

            active_after = await get_active_event()
            assert active_after is None

        run(scenario())

    def test_record_presence_and_generate_csv(self):
        async def scenario():
            event = await create_event(EventCreate(name="Treinamento Equipe"))

            async with session_scope() as session:
                person = Person(name="Carlos Lima", embedding=[0.1] * 512)
                session.add(person)
                await session.flush()
                person_id = person.id

            # Record first presence
            p_out = await record_event_presence(event.id, person_id)
            assert p_out is not None
            assert p_out.person_id == person_id
            assert p_out.display_name == "Carlos Lima"

            # Duplicate record returns None (idempotent)
            p_dup = await record_event_presence(event.id, person_id)
            assert p_dup is None

            # Get presence list
            presences = await get_event_presence(event.id)
            assert len(presences) == 1
            assert presences[0].display_name == "Carlos Lima"

            # Export CSV
            csv_data = await generate_event_csv(event.id)
            assert csv_data is not None
            assert "Carlos Lima" in csv_data
            assert "Treinamento Equipe" in csv_data
            assert "ID Presenca" in csv_data

        run(scenario())
