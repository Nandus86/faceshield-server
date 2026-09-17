"""Live camera manager: capture and inference run on decoupled threads.

The capture thread reads frames as fast as the camera delivers them and keeps
only the most recent one. A separate analysis thread periodically feeds that
frame through the unified RecognitionService (running inference in an
executor so it never blocks the capture), then draws the HUD over the frame
served to MJPEG clients. This keeps the live stream smooth even when CPU
inference takes hundreds of milliseconds.
"""

import asyncio
import logging
import os
import threading
import time
from collections import deque
from datetime import datetime
from typing import List, Optional

import cv2
import numpy as np

import config

logger = logging.getLogger(__name__)

COLOR_KNOWN = (34, 197, 94)     # green
COLOR_UNKNOWN = (239, 68, 68)   # red


class CameraManager:
    """Manages video capture, real-time recognition and MJPEG streaming."""

    def __init__(self):
        self.lock = threading.Lock()
        self.cap = None
        self.running = False

        self._capture_thread: Optional[threading.Thread] = None
        self._analysis_thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        self.latest_frame: Optional[np.ndarray] = None
        self.latest_jpeg: Optional[bytes] = None
        self.latest_results: List = []
        self.fps = 0.0
        self.status_message = "Pronto"

        self.camera_index = config.get_settings().CAMERA_INDEX
        self.use_a9 = config.get_settings().USE_A9_CAMERA
        self.analysis_interval = max(0.3, config.get_settings().ANALYSIS_INTERVAL)

        self.ai_insights = deque(maxlen=40)
        self._last_ai_analysis = 0.0

    # ── Lifecycle ─────────────────────────────────────────────

    def setup(self, loop: asyncio.AbstractEventLoop) -> None:
        """Store the main event loop; required before start()."""
        self._loop = loop

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._capture_thread = threading.Thread(target=self._capture_loop,
                                                name="camera-capture", daemon=True)
        self._analysis_thread = threading.Thread(target=self._analysis_loop,
                                                 name="camera-analysis", daemon=True)
        self._capture_thread.start()
        self._analysis_thread.start()

    def stop(self) -> None:
        self.running = False
        for thread in [self._capture_thread, self._analysis_thread]:
            if thread and thread.is_alive():
                thread.join(timeout=2.0)
        self._release_camera()
        self.status_message = "Câmera parada"

    def restart(self, camera_index=None, use_a9=None, analysis_interval=None) -> dict:
        with self.lock:
            if camera_index is not None:
                self.camera_index = int(camera_index)
            if use_a9 is not None:
                self.use_a9 = bool(use_a9)
            if analysis_interval is not None:
                self.analysis_interval = max(0.3, float(analysis_interval))
            settings = {
                "camera_index": self.camera_index,
                "use_a9": self.use_a9,
                "analysis_interval": self.analysis_interval,
            }
        self.stop()
        self.start()
        return settings

    # ── Camera handling ───────────────────────────────────────

    def _open_camera(self):
        if self.use_a9:
            try:
                import sys
                sys.path.insert(0, config.BASE_DIR)
                from a9_camera_adapter import A9VideoCapture
                cap = A9VideoCapture()
                if cap.isOpened():
                    return cap, "Câmera Wi-Fi A9 conectada"
                return None, "Falha na câmera A9 (tentando webcam USB)"
            except Exception as err:
                return None, f"Erro A9 ({err}); tentando webcam USB"

        if os.name != "nt":
            video_devices = [f"/dev/video{i}" for i in range(4)
                             if os.path.exists(f"/dev/video{i}")]
            if not video_devices:
                return None, "Servidor sem câmera USB (use a Webcam do Navegador ou RTSP)"

        backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
        cap = self._try_open(self.camera_index, backend)
        if cap is None and self.camera_index != 0:
            cap = self._try_open(0, backend)
            if cap is not None:
                self.camera_index = 0
        if cap is None:
            return None, f"Não foi possível abrir a câmera (índice {self.camera_index})"

        try:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)
        except Exception:
            pass
        label = "Câmera Wi-Fi A9" if self.use_a9 else f"Webcam (índice {self.camera_index})"
        return cap, f"{label} ativa"

    @staticmethod
    def _try_open(index: int, backend):
        try:
            cap = cv2.VideoCapture(index, backend)
            if cap.isOpened():
                return cap
            cap.release()
            cap = cv2.VideoCapture(index)
            if cap.isOpened():
                return cap
            cap.release()
        except Exception:
            pass
        return None

    def _release_camera(self):
        with self.lock:
            if self.cap is not None:
                try:
                    self.cap.release()
                except Exception:
                    pass
                self.cap = None

    # ── Threads ───────────────────────────────────────────────

    def _capture_loop(self):
        reconnect_delay = 3.0
        frames_this_second = 0
        last_fps_check = time.time()

        while self.running:
            with self.lock:
                cap = self.cap
            if cap is None or not cap.isOpened():
                cap, message = self._open_camera()
                with self.lock:
                    self.cap = cap
                    self.status_message = message
                    self.latest_frame = None
                if cap is None:
                    self._emit_blank_frame(message)
                    time.sleep(reconnect_delay)
                    continue

            ok, frame = cap.read()
            if not ok or frame is None:
                logger.warning("Frame inválido da câmera; reconectando...")
                self._release_camera()
                time.sleep(1.0)
                continue

            now = time.time()
            frames_this_second += 1
            if now - last_fps_check >= 1.0:
                self.fps = frames_this_second / (now - last_fps_check)
                frames_this_second = 0
                last_fps_check = now

            with self.lock:
                self.latest_frame = frame
            time.sleep(0.005)

    def _analysis_loop(self):
        while self.running:
            time.sleep(self.analysis_interval)

            if self._loop is None or not self._loop.is_running():
                continue

            with self.lock:
                frame = None if self.latest_frame is None else self.latest_frame.copy()

            if frame is None:
                continue

            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._analyze(frame.copy()), self._loop
                )
                outcomes = future.result(timeout=30.0)
            except Exception as err:
                logger.debug("Análise de frame ignorada: %s", err)
                continue

            annotated = self._draw_hud(frame, outcomes)
            ok, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                with self.lock:
                    self.latest_jpeg = jpeg.tobytes()
                    self.latest_results = [
                        {"status": o.status, "display_name": o.display_name}
                        for o in outcomes
                    ]

            self._maybe_run_ai_insights(outcomes)

    async def _analyze(self, frame):
        from core.recognition_service import recognition_service
        return await recognition_service.process_image(frame, source="camera")

    # ── HUD ───────────────────────────────────────────────────

    def _draw_hud(self, frame: np.ndarray, outcomes) -> np.ndarray:
        h, w = frame.shape[:2]

        for outcome in outcomes:
            if len(outcome.bbox) != 4:
                continue
            x1, y1, x2, y2 = [int(v) for v in outcome.bbox]
            color = COLOR_UNKNOWN if outcome.status in ("pending", "unknown") else COLOR_KNOWN

            corner = min(int((x2 - x1) * 0.25), 25)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            for (px, py, dx, dy) in [
                (x1, y1, 1, 1), (x2, y1, -1, 1),
                (x1, y2, 1, -1), (x2, y2, -1, -1),
            ]:
                cv2.line(frame, (px, py), (px + dx * corner, py), (255, 255, 255), 3)
                cv2.line(frame, (px, py), (px, py + dy * corner), (255, 255, 255), 3)

            label = f" {outcome.display_name} "
            font = cv2.FONT_HERSHEY_SIMPLEX
            (text_w, text_h), _ = cv2.getTextSize(label, font, 0.55, 1)
            badge_top = max(0, y1 - text_h - 12)
            cv2.rectangle(frame, (x1, badge_top), (min(w, x1 + text_w + 10), badge_top + text_h + 8),
                          color, cv2.FILLED)
            cv2.putText(frame, label, (x1 + 5, badge_top + text_h + 3),
                        font, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 32), (15, 23, 42), -1)
        cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)

        hud_text = f"AO VIVO | FPS {self.fps:.1f} | {datetime.now().strftime('%H:%M:%S')}"
        cv2.putText(frame, hud_text, (12, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (226, 232, 240), 1, cv2.LINE_AA)
        cv2.circle(frame, (w - 18, 16), 5, COLOR_KNOWN, -1)
        return frame

    def _emit_blank_frame(self, message: str):
        blank = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.rectangle(blank, (0, 0), (640, 480), (15, 23, 42), -1)
        cv2.putText(blank, "VisionAI FaceShield", (170, 200),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (241, 245, 249), 2, cv2.LINE_AA)
        cv2.putText(blank, "Aguardando camera USB - use Webcam do Navegador ou RTSP",
                    (90, 245), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (148, 163, 184), 1, cv2.LINE_AA)
        cv2.putText(blank, f"Status: {message}", (90, 285),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (56, 189, 248), 1, cv2.LINE_AA)
        ok, jpeg = cv2.imencode(".jpg", blank, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            with self.lock:
                self.latest_jpeg = jpeg.tobytes()

    # ── AI insights (optional) ────────────────────────────────

    def _maybe_run_ai_insights(self, outcomes):
        cfg = config.get_settings()
        if not cfg.AGENT_ENABLED or not outcomes:
            return
        now = time.monotonic()
        if now - self._last_ai_analysis < cfg.ANALYSIS_INTERVAL:
            return
        self._last_ai_analysis = now
        threading.Thread(target=self._run_ai_insights, args=(outcomes,), daemon=True).start()

    def _run_ai_insights(self, outcomes):
        try:
            from ai_agent.agent import get_agent
            agent = get_agent()
            if agent is None:
                return
            for outcome in outcomes:
                analysis = agent.analyze_detection(
                    outcome.display_name, outcome.status not in ("pending", "unknown")
                )
                text = analysis.get("analysis")
                if text:
                    self.ai_insights.appendleft({
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "text": text,
                        "type": "registered" if outcome.status != "pending" else "unknown",
                        "name": outcome.display_name,
                    })
        except Exception as err:
            logger.debug("Insights de IA indisponíveis: %s", err)

    # ── Accessors ─────────────────────────────────────────────

    def get_latest_jpeg(self) -> Optional[bytes]:
        with self.lock:
            return self.latest_jpeg

    def get_latest_raw_frame(self) -> Optional[np.ndarray]:
        with self.lock:
            return self.latest_frame.copy() if self.latest_frame is not None else None

    def get_status(self) -> dict:
        with self.lock:
            return {
                "fps": round(self.fps, 1),
                "status": self.status_message,
                "active": self.running,
                "results": list(self.latest_results),
            }


# Module-level singleton
camera_manager = CameraManager()
