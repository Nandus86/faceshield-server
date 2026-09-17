"""Async database layer: PostgreSQL + pgvector primary, SQLite local fallback."""

import logging
import os
import datetime
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import config
from core.models import AppSettings, Base, Event, EventPresence

logger = logging.getLogger(__name__)

SQLITE_PATH = os.path.join(config.DATA_DIR, "faceshield_local.db")
SQLITE_URL = f"sqlite+aiosqlite:///{SQLITE_PATH}"

_is_sqlite = False
engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def _build(url: str) -> None:
    global _is_sqlite, engine, _session_factory
    _is_sqlite = url.startswith("sqlite")
    if _is_sqlite:
        engine = create_async_engine(url, echo=False, poolclass=NullPool)
    else:
        engine = create_async_engine(url, echo=False, pool_pre_ping=True)
    _session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


_build(config.get_settings().DATABASE_URL)


def as_utc(value: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
    """Normalize DB datetimes to timezone-aware UTC (SQLite returns naive)."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


# Additive migrations applied on every startup (safe for existing databases).
_ADDITIVE_COLUMNS = {
    "persons": [
        ("sighting_count", "INTEGER NOT NULL DEFAULT 1"),
        ("first_seen_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
        ("last_seen_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ],
    "verification_logs": [
        ("is_new_registration", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ],
    "app_settings": [
        ("min_sightings", "INTEGER NOT NULL DEFAULT 2"),
        ("presence_timeout_seconds", "INTEGER NOT NULL DEFAULT 30"),
        ("auto_register_enabled", "BOOLEAN NOT NULL DEFAULT TRUE"),
        ("webhook_url", "VARCHAR(500)"),
        ("audio_alerts_enabled", "BOOLEAN NOT NULL DEFAULT TRUE"),
    ],
}


async def _apply_additive_migrations(conn) -> None:
    """Add newly introduced columns to pre-existing tables when possible."""
    dialect = conn.dialect.name

    for table, columns in _ADDITIVE_COLUMNS.items():
        for column_name, ddl in columns:
            try:
                if dialect == "postgresql":
                    await conn.execute(text(
                        f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS "{column_name}" {ddl}'
                    ))
                elif dialect == "sqlite":
                    info = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
                    existing = {row[1] for row in info.fetchall()}
                    if column_name not in existing:
                        await conn.execute(text(
                            f'ALTER TABLE {table} ADD COLUMN "{column_name}" {ddl}'
                        ))
            except Exception as err:
                logger.warning("Migração aditiva ignorada (%s.%s): %s",
                               table, column_name, err)


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Standalone session with automatic commit/rollback (services & tasks)."""
    if _session_factory is None:  # pragma: no cover
        raise RuntimeError("Database not initialized.")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a session with automatic commit/rollback."""
    async with session_scope() as session:
        yield session


async def init_db() -> bool:
    """Create tables/extension and seed default settings row.

    Falls back transparently to SQLite if PostgreSQL is unreachable.
    """
    global engine, _session_factory

    if not _is_sqlite:
        try:
            logger.info("Conectando ao PostgreSQL (%s)...", _safe_host())
            async with engine.begin() as conn:
                try:
                    await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                except Exception as ext_err:
                    logger.warning("Extensão vector indisponível: %s", ext_err)
                await conn.run_sync(Base.metadata.create_all)
                await _apply_additive_migrations(conn)
            logger.info("PostgreSQL inicializado.")
        except Exception as pg_err:
            logger.warning(
                "PostgreSQL inacessível (%s). Usando SQLite local em %s...",
                pg_err, SQLITE_PATH,
            )
            await engine.dispose()
            _build(SQLITE_URL)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                await _apply_additive_migrations(conn)
    else:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await _apply_additive_migrations(conn)
        logger.info("SQLite inicializado em %s.", SQLITE_PATH)

    # Ensure single settings row exists (id=1)
    async with session_scope() as session:
        result = await session.execute(select(AppSettings).where(AppSettings.id == 1))
        st = result.scalar_one_or_none()
        cfg = config.get_settings()
        if st is None:
            session.add(AppSettings(
                id=1,
                cooldown_minutes=cfg.COOLDOWN_MINUTES,
                similarity_threshold=cfg.SIMILARITY_THRESHOLD,
                image_retention_hours=cfg.IMAGE_RETENTION_HOURS,
                rtsp_frame_interval=cfg.RTSP_FRAME_INTERVAL,
                min_sightings=cfg.MIN_SIGHTINGS,
                presence_timeout_seconds=cfg.PRESENCE_TIMEOUT_SECONDS,
                auto_register_enabled=True,
            ))
            logger.info("Configurações padrão inseridas no banco.")
        elif st.similarity_threshold >= 0.40:
            st.similarity_threshold = cfg.SIMILARITY_THRESHOLD
            logger.info("Limiar de similaridade atualizado para %s (calibração contra falsos positivos).",
                        cfg.SIMILARITY_THRESHOLD)

    return True


async def dispose_engine() -> None:
    if engine is not None:
        await engine.dispose()


def is_using_sqlite() -> bool:
    return _is_sqlite


def _safe_host() -> str:
    url = config.get_settings().DATABASE_URL
    return url.split("@")[-1] if "@" in url else url
