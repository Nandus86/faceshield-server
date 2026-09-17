from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select

from core.database import session_scope
from core.models import Event, EventPresence
from core.schemas import EventCreate, EventOut, EventPresenceOut
from core.event_service import (
    create_event,
    end_event,
    list_events,
    get_active_event,
    get_event_presence,
    record_event_presence,
    generate_event_csv,
)

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.post("", response_model=EventOut)
async def create_event_endpoint(payload: EventCreate):
    return await create_event(payload)


@router.get("/active", response_model=EventOut | None)
async def get_active_event_endpoint():
    return await get_active_event()


@router.get("", response_model=list[EventOut])
async def list_events_endpoint(limit: int = 50):
    return await list_events(limit=limit)


@router.post("/{event_id}/end", response_model=EventOut)
async def end_event_endpoint(event_id: int):
    result = await end_event(event_id)
    if not result:
        raise HTTPException(status_code=404, detail="Evento não encontrado.")
    return result


@router.get("/{event_id}/presence", response_model=list[EventPresenceOut])
async def get_event_presence_endpoint(event_id: int):
    return await get_event_presence(event_id)


@router.post("/{event_id}/presence/{person_id}", response_model=EventPresenceOut | None)
async def record_presence_endpoint(event_id: int, person_id: int):
    return await record_event_presence(event_id, person_id)


@router.get("/{event_id}/export.csv")
async def export_event_csv_endpoint(event_id: int):
    """Export event attendance as a CSV file."""
    csv_content = await generate_event_csv(event_id)
    if csv_content is None:
        raise HTTPException(status_code=404, detail="Evento não encontrado.")

    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=presenca_evento_{event_id}.csv",
        },
    )
