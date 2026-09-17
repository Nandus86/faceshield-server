"""YouTube video ingestion: download with yt-dlp and frame analysis via the
unified recognition pipeline, streaming progress over SSE."""

import asyncio
import json
import logging
import os
import re
import tempfile
from typing import AsyncGenerator, Optional

import cv2

import config
from core.recognition_service import recognition_service
from core.schemas import YouTubeRequest

logger = logging.getLogger(__name__)


def extract_video_id(url: str) -> Optional[str]:
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",
        r"(?:youtu\.be\/)([0-9A-Za-z_-]{11})",
        r"(?:embed\/)([0-9A-Za-z_-]{11})",
        r"(?:shorts\/)([0-9A-Za-z_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


async def _download_video(url: str, output_path: str) -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "yt-dlp",
            "-f", "best[height<=720][ext=mp4]/best[height<=720]/best[ext=mp4]/best",
            "--no-playlist",
            "--socket-timeout", "60",
            "--force-ipv4",
            "--extractor-args", "youtube:player_client=android;youtube:skip=webpage",
            "-o", output_path,
            url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error("yt-dlp erro: %s", stderr.decode(errors="ignore").strip()[:500])
        return proc.returncode == 0
    except FileNotFoundError:
        logger.error("yt-dlp não encontrado no PATH.")
        return False
    except Exception as err:
        logger.error("Falha ao executar yt-dlp: %s", err)
        return False


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def process_video(video_path: str, req: YouTubeRequest) -> AsyncGenerator[str, None]:
    """Analyze downloaded video frames, yielding SSE events."""
    cap = await asyncio.get_running_loop().run_in_executor(
        None, lambda: _open_video(video_path)
    )
    if cap is None:
        yield _sse({"type": "error", "message": "Não foi possível abrir o vídeo baixado."})
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(1, int(fps * max(0.2, req.frame_interval)))
    registered_ids = set()
    frame_num = 0

    yield _sse({"type": "info",
                "message": f"Vídeo carregado. {total_frames} frames @ {fps:.1f} FPS."})

    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                break

            current_index = frame_num
            frame_num += 1
            if current_index % step != 0:
                continue

            seconds = round(current_index / fps, 1)
            progress = round(current_index / total_frames * 100, 1) if total_frames else 0

            outcomes = await recognition_service.process_image(
                frame,
                source="youtube",
                return_images=True,
                min_face_size=req.min_face_size,
                min_det_score=req.min_det_score,
            )

            for outcome in outcomes:
                if outcome.person_id is not None and outcome.status == "registered":
                    registered_ids.add(outcome.person_id)
                yield _sse({
                    "type": "face",
                    "person_id": outcome.person_id,
                    "name": outcome.display_name,
                    "status": outcome.status,
                    "confidence": outcome.confidence,
                    "is_new": outcome.status == "registered",
                    "time": seconds,
                    "bbox": outcome.bbox,
                    "face_image": outcome.face_b64,
                })

            yield _sse({"type": "progress", "time": seconds, "progress": progress})
            await asyncio.sleep(0.005)
    finally:
        cap.release()
        try:
            os.unlink(video_path)
        except OSError:
            pass

    yield _sse({
        "type": "done",
        "total_persons": len(registered_ids),
        "message": f"Análise concluída. {len(registered_ids)} pessoa(s) nova(s) registrada(s).",
    })


def _open_video(path: str):
    cap = cv2.VideoCapture(path)
    return cap if cap.isOpened() else None


async def create_youtube_stream(req: YouTubeRequest) -> AsyncGenerator[str, None]:
    """Full SSE flow: validate URL, download, analyze."""
    video_id = extract_video_id(req.url)
    if not video_id:
        yield _sse({"type": "error", "message": "URL do YouTube inválida."})
        return

    temp_dir = tempfile.mkdtemp(prefix="faceshield_yt_")
    video_path = os.path.join(temp_dir, f"{video_id}.mp4")

    yield _sse({"type": "info", "message": "Baixando vídeo do YouTube..."})
    if not await _download_video(req.url, video_path):
        yield _sse({"type": "error",
                    "message": "Falha ao baixar o vídeo. Verifique a URL e o yt-dlp."})
        return

    yield _sse({"type": "info", "message": "Download concluído. Iniciando análise facial..."})

    async for event in process_video(video_path, req):
        yield event
