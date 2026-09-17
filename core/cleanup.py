"""Periodic background cleanup of expired face/frame images."""

import asyncio
import datetime
import logging
from pathlib import Path

from sqlalchemy import select, update

import config
from core.database import is_using_sqlite, session_scope
from core.models import AppSettings, VerificationLog

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


async def _get_retention_hours() -> int:
    try:
        async with session_scope() as session:
            result = await session.execute(select(AppSettings).where(AppSettings.id == 1))
            settings_row = result.scalar_one_or_none()
            if settings_row:
                return settings_row.image_retention_hours
    except Exception:
        pass
    return config.get_settings().IMAGE_RETENTION_HOURS


async def cleanup_old_images(data_dir: str = config.DATA_DIR) -> int:
    """Delete image files older than the retention period and null their log refs."""
    retention_hours = await _get_retention_hours()
    cutoff_local = datetime.datetime.now() - datetime.timedelta(hours=retention_hours)
    deleted = 0
    deleted_paths = []

    data_path = Path(data_dir)
    for directory_name in ["frames", "faces"]:
        directory = data_path / directory_name
        if not directory.exists():
            continue
        for file in directory.iterdir():
            if not file.is_file() or file.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            try:
                mtime = datetime.datetime.fromtimestamp(file.stat().st_mtime)
                if mtime < cutoff_local:
                    file.unlink(missing_ok=True)
                    deleted += 1
                    deleted_paths.append(str(file))
            except Exception as err:
                logger.warning("Falha ao remover arquivo antigo %s: %s", file, err)

    # Null out references to files that no longer exist.
    if deleted > 0:
        try:
            cutoff_utc = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
                hours=retention_hours
            )
            if is_using_sqlite():
                db_cutoff = cutoff_utc.replace(tzinfo=None)  # SQLite stores naive UTC
            else:
                db_cutoff = cutoff_utc

            deleted_set = set(deleted_paths)
            async with session_scope() as session:
                result = await session.execute(
                    select(VerificationLog.id, VerificationLog.frame_image_path)
                    .where(VerificationLog.frame_image_path.is_not(None),
                           VerificationLog.detected_at < db_cutoff)
                )
                stale_ids = [
                    row_id for row_id, path in result.all()
                    if path in deleted_set
                ]
                if stale_ids:
                    await session.execute(
                        update(VerificationLog)
                        .where(VerificationLog.id.in_(stale_ids))
                        .values(frame_image_path=None)
                    )
        except Exception as err:
            logger.warning("Aviso ao limpar referências de logs: %s", err)

    if deleted > 0:
        logger.info("Limpeza periódica: %d imagem(ns) antiga(s) excluída(s).", deleted)
    return deleted


async def cleanup_loop(data_dir: str = config.DATA_DIR,
                       interval_hours: float = 1) -> None:
    """Background task running the cleanup periodically."""
    logger.info("Serviço de limpeza de imagens iniciado (intervalo: %.1fh).", interval_hours)
    while True:
        try:
            await cleanup_old_images(data_dir)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            logger.exception("Erro no loop de limpeza: %s", err)
        await asyncio.sleep(interval_hours * 3600)
