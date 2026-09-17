"""Live camera endpoints: MJPEG feed, camera configuration, AI insights."""

import asyncio
import logging
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

import config
from core.camera_manager import camera_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["camera"])


def _mjpeg_generator():
    while True:
        frame_bytes = camera_manager.get_latest_jpeg()
        if frame_bytes is None:
            time.sleep(0.1)
            continue
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
        time.sleep(0.033)


@router.get("/video_feed")
async def video_feed():
    """Live MJPEG stream with HUD detection overlay."""
    return StreamingResponse(
        _mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/camera_status")
async def camera_status():
    return camera_manager.get_status()


class CameraConfig(BaseModel):
    camera_index: Optional[int] = None
    use_a9: Optional[bool] = None
    analysis_interval: Optional[float] = None


@router.post("/camera_config")
async def update_camera_config(cfg: CameraConfig):
    """Update camera settings and restart the capture worker."""
    settings = camera_manager.restart(
        camera_index=cfg.camera_index,
        use_a9=cfg.use_a9,
        analysis_interval=cfg.analysis_interval,
    )
    return {"success": True, **settings, "status": camera_manager.get_status()["status"]}


@router.get("/ai_insights")
async def ai_insights():
    """Latest behavioral insights from the optional AI agent."""
    return list(camera_manager.ai_insights)


@router.post("/generate_summary")
async def generate_summary():
    """Generate an executive summary via the AI agent (if configured)."""
    from ai_agent.agent import get_agent
    agent = get_agent()
    if agent is None:
        return {"summary": "Agente de IA indisponível: configure OPENAI_API_KEY no .env."}
    summary = await asyncio.get_running_loop().run_in_executor(None, agent.get_summary)
    return {"summary": summary or "Não foi possível gerar o resumo agora."}
