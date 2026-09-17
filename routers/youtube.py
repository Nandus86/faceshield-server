"""POST /api/v1/youtube/process — SSE stream of video download + face analysis."""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from core.schemas import YouTubeRequest
from core.youtube_service import create_youtube_stream

router = APIRouter(prefix="/api/v1/youtube", tags=["youtube"])


@router.post("/process")
async def process_youtube(req: YouTubeRequest):
    """Download and analyze a YouTube video, streaming events via SSE."""
    return StreamingResponse(
        create_youtube_stream(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
