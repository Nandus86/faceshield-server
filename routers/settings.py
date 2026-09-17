"""GET/PUT /api/v1/settings — runtime application settings."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import config
from core.database import get_db
from core.models import AppSettings
from core.schemas import AppSettingsOut, AppSettingsUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


async def _ensure_settings(session: AsyncSession) -> AppSettings:
    result = await session.execute(select(AppSettings).where(AppSettings.id == 1))
    st = result.scalar_one_or_none()
    if st is None:
        cfg = config.get_settings()
        st = AppSettings(
            id=1,
            cooldown_minutes=cfg.COOLDOWN_MINUTES,
            similarity_threshold=cfg.SIMILARITY_THRESHOLD,
            image_retention_hours=cfg.IMAGE_RETENTION_HOURS,
            rtsp_frame_interval=cfg.RTSP_FRAME_INTERVAL,
            min_sightings=cfg.MIN_SIGHTINGS,
            presence_timeout_seconds=cfg.PRESENCE_TIMEOUT_SECONDS,
            auto_register_enabled=True,
        )
        session.add(st)
        await session.commit()
        await session.refresh(st)
    elif st.similarity_threshold >= 0.60:
        st.similarity_threshold = cfg.SIMILARITY_THRESHOLD
        await session.commit()
        await session.refresh(st)
    return st


@router.get("", response_model=AppSettingsOut)
async def get_settings(session: AsyncSession = Depends(get_db)):
    return await _ensure_settings(session)


@router.put("", response_model=AppSettingsOut)
async def update_settings(
    data: AppSettingsUpdate,
    session: AsyncSession = Depends(get_db),
):
    """Update runtime settings (applied immediately, no restart needed)."""
    st = await _ensure_settings(session)

    changes = data.model_dump(exclude_none=True)
    for field_name, value in changes.items():
        setattr(st, field_name, value)

    await session.commit()
    await session.refresh(st)
    logger.info("Configurações atualizadas: %s", changes)
    return st
