"""RTSP stream consumer: reads frames from IP camera streams in background threads."""

import asyncio
import logging
import time
import threading
from typing import Callable, Awaitable, Dict, Optional
import cv2
import numpy as np

logger = logging.getLogger(__name__)


class RTSPConsumer:
    """Manages a single RTSP stream, capturing frames at a configurable interval."""

    def __init__(
        self,
        stream_id: int,
        stream_name: str,
        url: str,
        frame_interval: float = 2.0,
        on_frame: Optional[Callable[[int, str, np.ndarray], Awaitable[None]]] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        self.stream_id = stream_id
        self.stream_name = stream_name
        self.url = url
        self.frame_interval = frame_interval
        self._on_frame = on_frame
        self._loop = loop
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._cap: Optional[cv2.VideoCapture] = None

    def start(self) -> None:
        """Start the background RTSP capture thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop,
            name=f"rtsp-{self.stream_id}",
            daemon=True,
        )
        self._thread.start()
        logger.info("Iniciado consumidor RTSP para '%s' (%s)", self.stream_name, self.url)

    def stop(self) -> None:
        """Stop the background RTSP capture thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        if self._cap and self._cap.isOpened():
            try:
                self._cap.release()
            except Exception:
                pass
        logger.info("Consumidor RTSP '%s' finalizado.", self.stream_name)

    @property
    def is_running(self) -> bool:
        return self._running

    def _capture_loop(self) -> None:
        reconnect_delay = 5.0
        max_reconnect_delay = 60.0

        while self._running:
            try:
                # Open video stream
                self._cap = cv2.VideoCapture(self.url)
                if not self._cap or not self._cap.isOpened():
                    logger.warning(
                        "Falha ao conectar no stream RTSP '%s'. Nova tentativa em %.0fs...",
                        self.stream_name,
                        reconnect_delay,
                    )
                    time.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
                    continue

                reconnect_delay = 5.0
                logger.info("Conexão RTSP estabelecida com '%s'", self.stream_name)

                while self._running:
                    ret, frame = self._cap.read()
                    if not ret or frame is None:
                        logger.warning("Sinal perdido em '%s'. Reconectando...", self.stream_name)
                        break

                    # Dispatch frame to async callback
                    if self._on_frame and self._loop and self._loop.is_running():
                        try:
                            asyncio.run_coroutine_threadsafe(
                                self._on_frame(self.stream_id, self.stream_name, frame),
                                self._loop,
                            )
                        except Exception as cb_err:
                            logger.error("Erro ao despachar frame RTSP: %s", cb_err)

                    time.sleep(self.frame_interval)

            except Exception as e:
                logger.exception("Exceção no consumidor RTSP '%s': %s", self.stream_name, e)
                time.sleep(reconnect_delay)
            finally:
                if self._cap and self._cap.isOpened():
                    try:
                        self._cap.release()
                    except Exception:
                        pass


class RTSPManager:
    """Manages multiple active RTSP consumers."""

    def __init__(self):
        self._consumers: Dict[int, RTSPConsumer] = {}
        self._on_frame: Optional[Callable[[int, str, np.ndarray], Awaitable[None]]] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_callback(
        self,
        on_frame: Callable[[int, str, np.ndarray], Awaitable[None]],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._on_frame = on_frame
        self._loop = loop

    def start_stream(
        self,
        stream_id: int,
        stream_name: str,
        url: str,
        frame_interval: float = 2.0,
    ) -> None:
        if stream_id in self._consumers and self._consumers[stream_id].is_running:
            return

        consumer = RTSPConsumer(
            stream_id=stream_id,
            stream_name=stream_name,
            url=url,
            frame_interval=frame_interval,
            on_frame=self._on_frame,
            loop=self._loop,
        )
        self._consumers[stream_id] = consumer
        consumer.start()

    def stop_stream(self, stream_id: int) -> None:
        consumer = self._consumers.get(stream_id)
        if consumer:
            consumer.stop()
            del self._consumers[stream_id]

    def stop_all(self) -> None:
        for consumer in list(self._consumers.values()):
            consumer.stop()
        self._consumers.clear()

    def is_running(self, stream_id: int) -> bool:
        consumer = self._consumers.get(stream_id)
        return consumer.is_running if consumer else False


# Module-level singleton
rtsp_manager = RTSPManager()
