"""Centralized application configuration (pydantic-settings).

All runtime configuration is loaded from environment variables / .env file.
Access it via `get_settings()` anywhere in the codebase.
"""

import os
from functools import lru_cache
from pydantic_settings import BaseSettings

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
FACES_DIR = os.path.join(DATA_DIR, "faces")
FRAMES_DIR = os.path.join(DATA_DIR, "frames")


def ensure_directories() -> None:
    """Create all required data directories."""
    for directory in [DATA_DIR, FACES_DIR, FRAMES_DIR]:
        os.makedirs(directory, exist_ok=True)


class Settings(BaseSettings):
    """Unified application settings loaded from environment / .env file."""

    # ── Database ──────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://faceshield:faceshield_secret@localhost:5432/faceshield"

    # ── Face recognition (InsightFace ArcFace 512-d) ─────────
    FACE_MODEL: str = "buffalo_l"
    DET_SIZE: int = 320                # Detection input size (320 fastest CPU / 640 balanced / 1280 more accurate)
    SIMILARITY_THRESHOLD: float = 0.45 # Cosine distance threshold (lower = stricter; 0.45 = ~55% similarity)
    MIN_FACE_SIZE: int = 40            # Minimum face width/height in pixels
    MIN_DET_SCORE: float = 0.40        # Minimum detection confidence (0-1)
    COOLDOWN_MINUTES: int = 60         # Minutes between re-logging the same person
    MIN_SIGHTINGS: int = 2             # Sightings required before auto-registering a stranger
    SIGHTING_TTL_MINUTES: int = 10     # How long pending sightings of unknowns are kept

    # ── Storage & retention ──────────────────────────────────
    DATA_DIR: str = DATA_DIR
    IMAGE_RETENTION_HOURS: int = 48    # Delete face crops/frames older than this
    CLEANUP_INTERVAL_HOURS: int = 1    # Interval between cleanup cycles

    # ── Camera & ingestion ───────────────────────────────────
    CAMERA_INDEX: int = 0
    USE_A9_CAMERA: bool = False
    RTSP_FRAME_INTERVAL: float = 2.0   # Seconds between frame captures per stream
    ANALYSIS_INTERVAL: float = 0.5     # Seconds between inference passes on live camera
    PRESENCE_TIMEOUT_SECONDS: int = 30 # Seconds without detection before presence session ends

    # ── AI Agent (LangGraph + OpenAI) ────────────────────────
    AGENT_ENABLED: bool = True
    AGENT_MODEL: str = "gpt-4o-mini"

    # ── Security & Network ───────────────────────────────────
    ALLOWED_ORIGINS: str = "*"
    MAX_UPLOAD_SIZE_MB: int = 15

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Ensure directories exist on import (safe idempotent)
ensure_directories()
