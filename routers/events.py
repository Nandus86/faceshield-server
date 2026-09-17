"""GET /api/events — Server-Sent Events stream of live system events."""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from core.events import event_bus

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/events")
async def events_stream():
    """Subscribe to real-time events (person_registered, recognition, presence_ended)."""
    return StreamingResponse(
        event_bus.stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
