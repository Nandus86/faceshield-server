"""VisionAI FaceShield — FastAPI application.

Thin composition root: wires the database, the recognition engine, background
services (camera, RTSP, cleanup, presence timeout) and the HTTP API together.
All business logic lives in core/ services and routers/.
"""

import asyncio
import logging
import os
import sys

# Silence low-level OpenCV / FFMPEG C++ logs
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
os.environ["OPENCV_VIDEOIO_DEBUG"] = "0"
os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "-8"

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import cv2
try:
    cv2.setLogLevel(0)
except Exception:
    pass

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

import config
from core.camera_manager import camera_manager
from core.cleanup import cleanup_loop
from core.database import init_db, is_using_sqlite, session_scope
from core.events import event_bus
from core.face_engine import face_engine
from core.models import RTSPStream
from core.presence_service import get_timeout_seconds, presence_timeout_task
from core.recognition_service import recognition_service
from core.rtsp_consumer import rtsp_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("faceshield")

STATIC_DIR = os.path.join(config.BASE_DIR, "static")

# ─── Routers ──────────────────────────────────────────────────

from routers import verify, persons, streams, youtube          # noqa: E402
from routers import settings as settings_router                # noqa: E402
from routers import local_camera, dashboard, events, camera    # noqa: E402
from routers import event_management                            # noqa: E402


async def _process_rtsp_frame(stream_id: int, stream_name: str, frame) -> None:
    """RTSP callback — runs on the main event loop via the unified pipeline."""
    try:
        await recognition_service.process_image(frame, source=stream_name)
    except Exception:
        logger.exception("Erro ao processar frame do stream '%s'.", stream_name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Inicializando VisionAI FaceShield...")

    # 1. Database (+ fallback to SQLite when PostgreSQL is unreachable)
    await init_db()

    # 2. Deep learning engine
    loaded = await asyncio.get_running_loop().run_in_executor(None, face_engine.load)
    if not loaded:
        logger.warning("InsightFace indisponível; detecções ficarão desativadas.")

    # 3. Recognition cache from database
    await recognition_service.reload_cache()

    # 4. Event bus + camera manager on this loop
    loop = asyncio.get_running_loop()
    event_bus.setup(loop)
    camera_manager.setup(loop)

    # 5. RTSP consumers + resume previously active streams
    rtsp_manager.set_callback(_process_rtsp_frame, loop)
    async with session_scope() as session:
        result = await session.execute(
            select(RTSPStream).where(RTSPStream.is_active.is_(True))
        )
        active_streams = list(result.scalars().all())
    for stream in active_streams:
        rtsp_manager.start_stream(stream_id=stream.id, stream_name=stream.name, url=stream.url)
        logger.info("Câmera RTSP '%s' restaurada.", stream.name)

    # 6. Background tasks
    cleanup_task = asyncio.create_task(
        cleanup_loop(data_dir=config.DATA_DIR,
                     interval_hours=config.get_settings().CLEANUP_INTERVAL_HOURS)
    )
    presence_task = asyncio.create_task(presence_timeout_task(get_timeout_seconds))

    # 7. Live USB/A9 camera
    camera_manager.start()

    logger.info("Sistema pronto. Dashboard: http://localhost:%s", 8000)
    yield

    logger.info("Encerrando serviços...")
    camera_manager.stop()
    rtsp_manager.stop_all()
    for task in [cleanup_task, presence_task]:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="VisionAI FaceShield",
    description=(
        "Detecção e registro automático de pessoas com InsightFace (ArcFace 512-d), "
        "PostgreSQL/pgvector, câmeras RTSP/USB/A9, análise de vídeos e dashboard em tempo real."
    ),
    version="3.0.0",
    lifespan=lifespan,
)

origins_raw = config.get_settings().ALLOWED_ORIGINS
allowed_origins = [o.strip() for o in origins_raw.split(",") if o.strip()] if origins_raw != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router)
app.include_router(events.router)
app.include_router(event_management.router)
app.include_router(camera.router)
app.include_router(verify.router)
app.include_router(persons.router)
app.include_router(streams.router)
app.include_router(youtube.router)
app.include_router(settings_router.router)
app.include_router(local_camera.router)


@app.get("/health", tags=["health"])
async def health():
    return {
        "status": "healthy",
        "insightface_loaded": face_engine.is_available(),
        "database": "sqlite_fallback" if is_using_sqlite() else "pgvector",
    }


# ─── Static assets & data mounts ─────────────────────────────

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static_assets")
app.mount("/faces", StaticFiles(directory=config.FACES_DIR), name="faces_images")
app.mount("/frames", StaticFiles(directory=config.FRAMES_DIR), name="frames_images")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>VisionAI FaceShield</h1><p>index.html não encontrado.</p>")


if __name__ == "__main__":
    uvicorn.run("web_server:app", host="0.0.0.0", port=8000, reload=False)
