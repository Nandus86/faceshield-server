"""CRUD /api/v1/streams — manage and control RTSP camera streams."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import config
from core.database import get_db
from core.models import AppSettings, RTSPStream
from core.rtsp_consumer import rtsp_manager
from core.schemas import RTSPStreamCreate, RTSPStreamOut, RTSPStreamUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/streams", tags=["streams"])


async def _get_stream_or_404(session: AsyncSession, stream_id: int) -> RTSPStream:
    result = await session.execute(select(RTSPStream).where(RTSPStream.id == stream_id))
    stream = result.scalar_one_or_none()
    if not stream:
        raise HTTPException(status_code=404, detail="Stream RTSP não encontrado.")
    return stream


@router.get("", response_model=List[RTSPStreamOut])
async def list_streams(session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(RTSPStream).order_by(RTSPStream.created_at))
    streams = result.scalars().all()
    for stream in streams:
        stream.is_active = rtsp_manager.is_running(stream.id)
    return streams


@router.post("", response_model=RTSPStreamOut, status_code=201)
async def create_stream(data: RTSPStreamCreate, session: AsyncSession = Depends(get_db)):
    stream = RTSPStream(name=data.name.strip(), url=data.url.strip())
    session.add(stream)
    await session.commit()
    await session.refresh(stream)
    return stream


@router.put("/{stream_id}", response_model=RTSPStreamOut)
async def update_stream(
    stream_id: int,
    data: RTSPStreamUpdate,
    session: AsyncSession = Depends(get_db),
):
    """Update name/URL. Stops the stream first if it is running."""
    stream = await _get_stream_or_404(session, stream_id)

    if rtsp_manager.is_running(stream_id):
        rtsp_manager.stop_stream(stream_id)
        stream.is_active = False

    if data.name is not None:
        stream.name = data.name.strip()
    if data.url is not None:
        stream.url = data.url.strip()

    await session.commit()
    await session.refresh(stream)
    return stream


@router.delete("/{stream_id}")
async def delete_stream(stream_id: int, session: AsyncSession = Depends(get_db)):
    stream = await _get_stream_or_404(session, stream_id)

    if rtsp_manager.is_running(stream_id):
        rtsp_manager.stop_stream(stream_id)

    await session.delete(stream)
    await session.commit()
    return {"detail": "Câmera RTSP excluída com sucesso."}


@router.post("/{stream_id}/start")
async def start_stream(stream_id: int, session: AsyncSession = Depends(get_db)):
    """Start background consumption + recognition for this camera."""
    stream = await _get_stream_or_404(session, stream_id)

    if rtsp_manager.is_running(stream_id):
        return {"detail": f"Câmera '{stream.name}' já está em execução."}

    rt_result = await session.execute(select(AppSettings).where(AppSettings.id == 1))
    settings_row = rt_result.scalar_one_or_none()
    interval = (settings_row.rtsp_frame_interval if settings_row
                else config.get_settings().RTSP_FRAME_INTERVAL)

    rtsp_manager.start_stream(
        stream_id=stream.id,
        stream_name=stream.name,
        url=stream.url,
        frame_interval=interval,
    )
    stream.is_active = True
    await session.commit()

    logger.info("Stream RTSP '%s' iniciado.", stream.name)
    return {"detail": f"Câmera '{stream.name}' iniciada com sucesso."}


@router.post("/{stream_id}/stop")
async def stop_stream(stream_id: int, session: AsyncSession = Depends(get_db)):
    stream = await _get_stream_or_404(session, stream_id)

    if not rtsp_manager.is_running(stream_id):
        return {"detail": "Câmera não está em execução."}

    rtsp_manager.stop_stream(stream_id)
    stream.is_active = False
    await session.commit()
    return {"detail": f"Câmera '{stream.name}' parada com sucesso."}
