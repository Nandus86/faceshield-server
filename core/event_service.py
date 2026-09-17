import csv
import io
import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, func

from core.database import as_utc, session_scope
from core.models import Event, EventPresence, Person
from core.schemas import EventCreate, EventOut, EventPresenceOut, image_url_for

logger = logging.getLogger(__name__)


async def create_event(payload: EventCreate) -> EventOut:
    async with session_scope() as session:
        event = Event(
            name=payload.name,
        )
        session.add(event)
        await session.flush()
        await session.refresh(event)
        return EventOut(
            id=event.id,
            name=event.name,
            started_at=event.started_at,
            ended_at=event.ended_at,
            created_at=event.created_at,
            is_active=event.is_active,
        )


async def end_event(event_id: int) -> Optional[EventOut]:
    async with session_scope() as session:
        result = await session.execute(select(Event).where(Event.id == event_id))
        event = result.scalar_one_or_none()
        if not event:
            return None
        event.ended_at = datetime.now(timezone.utc)
        await session.flush()
        await session.refresh(event)
        return EventOut(
            id=event.id,
            name=event.name,
            started_at=event.started_at,
            ended_at=event.ended_at,
            created_at=event.created_at,
            is_active=event.is_active,
        )


async def get_active_event() -> Optional[EventOut]:
    async with session_scope() as session:
        result = await session.execute(
            select(Event).where(Event.ended_at.is_(None)).order_by(Event.started_at.desc()).limit(1)
        )
        event = result.scalar_one_or_none()
        if not event:
            return None
        return EventOut(
            id=event.id,
            name=event.name,
            started_at=event.started_at,
            ended_at=event.ended_at,
            created_at=event.created_at,
            is_active=event.is_active,
        )


async def list_events(limit: int = 50) -> List[EventOut]:
    async with session_scope() as session:
        result = await session.execute(select(Event).order_by(Event.started_at.desc()).limit(limit))
        events = result.scalars().all()
        return [
            EventOut(
                id=e.id,
                name=e.name,
                started_at=e.started_at,
                ended_at=e.ended_at,
                created_at=e.created_at,
                is_active=e.is_active,
            )
            for e in events
        ]


async def record_event_presence(event_id: int, person_id: int, face_image_path: Optional[str] = None) -> Optional[EventPresenceOut]:
    """Record first presence of a person in an event. Idempotent per event+person."""
    async with session_scope() as session:
        result = await session.execute(
            select(EventPresence).where(
                EventPresence.event_id == event_id,
                EventPresence.person_id == person_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return None

        presence = EventPresence(
            event_id=event_id,
            person_id=person_id,
            face_image_path=face_image_path,
        )
        session.add(presence)
        await session.flush()
        await session.refresh(presence)

        person = await session.get(Person, person_id)
        display_name = person.display_name if person else f"Pessoa #{person_id}"
        photo_url = image_url_for(face_image_path)
        if not photo_url and person is not None:
            photo_url = image_url_for(person.face_image_path)

        return EventPresenceOut(
            id=presence.id,
            event_id=presence.event_id,
            person_id=presence.person_id,
            display_name=display_name,
            face_image_url=photo_url,
            first_seen_at=presence.first_seen_at,
        )


async def get_event_presence(event_id: int) -> List[EventPresenceOut]:
    async with session_scope() as session:
        result = await session.execute(
            select(EventPresence).where(EventPresence.event_id == event_id).order_by(EventPresence.first_seen_at.asc())
        )
        presences = result.scalars().all()
        out = []
        for p in presences:
            person = await session.get(Person, p.person_id)
            display_name = person.display_name if person else f"Pessoa #{p.person_id}"
            photo_url = image_url_for(p.face_image_path)
            if not photo_url and person is not None:
                photo_url = image_url_for(person.face_image_path)
            out.append(EventPresenceOut(
                id=p.id,
                event_id=p.event_id,
                person_id=p.person_id,
                display_name=display_name,
                face_image_url=photo_url,
                first_seen_at=p.first_seen_at,
            ))
        return out


async def generate_event_csv(event_id: int) -> Optional[str]:
    """Generate CSV string of presences in a given event."""
    async with session_scope() as session:
        result = await session.execute(select(Event).where(Event.id == event_id))
        event = result.scalar_one_or_none()
        if not event:
            return None

        presences = await get_event_presence(event_id)

    output = io.StringIO()
    # Write UTF-8 BOM for Excel compatibility
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["ID Presenca", "ID Evento", "Nome do Evento", "ID Pessoa", "Nome / Identificacao", "Primeiro Avistamento"])

    for p in presences:
        dt_str = p.first_seen_at.strftime("%d/%m/%Y %H:%M:%S") if p.first_seen_at else ""
        writer.writerow([p.id, p.event_id, event.name, p.person_id, p.display_name, dt_str])

    return output.getvalue()

