"""Face detection and embedding engine using InsightFace (ArcFace 512-d)."""

import logging
import os
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

import config

logger = logging.getLogger(__name__)

# Ensure CPU provider is configured for ONNX Runtime by default
os.environ["ORT_PROVIDERS"] = "CPUExecutionProvider"

# Images with min side below this threshold use the small-scale detector,
# because upscaling a tight face crop to a large det_size makes the
# detector miss the face entirely (anchor scale range limitation).
SMALL_IMAGE_MIN_SIDE = 480
SMALL_DET_SIZE = 320


@dataclass
class DetectedFace:
    """A single detected face with its embedding, bounding box, score, landmarks and cropped face."""
    bbox: list[float]                        # [x1, y1, x2, y2]
    embedding: np.ndarray                    # 512-d float32 vector (L2 normalized)
    det_score: float                         # detection confidence (0.0 to 1.0)
    face_image: np.ndarray                   # cropped face region (BGR format)
    kps: Optional[List[List[float]]] = None  # 5 facial landmarks [[x,y],...]


class FaceEngine:
    """Singleton-style face detection + 512-d embedding extraction engine.

    Uses InsightFace's buffalo_l (or configured model) with ONNX Runtime.
    Keeps a secondary small-scale detector for tight face crops.
    """

    def __init__(self, model_name: Optional[str] = None):
        self._model_name = model_name or config.get_settings().FACE_MODEL
        self._app = None
        self._app_small = None
        self._is_loaded = False

    def load(self) -> bool:
        """Load the InsightFace model. Call once on application startup."""
        if self._is_loaded and self._app is not None:
            return True

        det_size = max(160, int(config.get_settings().DET_SIZE))
        try:
            from insightface.app import FaceAnalysis
            self._app = FaceAnalysis(name=self._model_name)
            self._app.prepare(ctx_id=-1, det_size=(det_size, det_size))
            self._is_loaded = True
            logger.info("Modelo InsightFace carregado (det_size=%d).", det_size)
            return True
        except Exception as err:
            logger.warning("Falha ao carregar InsightFace com det_size=%d (%s). "
                           "Tentando 640...", det_size, err)
            try:
                from insightface.app import FaceAnalysis
                self._app = FaceAnalysis(name=self._model_name)
                self._app.prepare(ctx_id=-1, det_size=(640, 640))
                self._is_loaded = True
                logger.info("Modelo InsightFace carregado (det_size=640).")
                return True
            except Exception as err2:
                logger.exception("Não foi possível inicializar o InsightFace: %s", err2)
                self._app = None
                self._is_loaded = False
                return False

    def _small_detector(self):
        """Return a detector suited to tight crops.

        When the main detector already runs at (or below) the small scale, it is
        reused directly — no second model is loaded, saving memory and avoiding
        a slow lazy load on the first small crop.
        """
        if self._app_small is None:
            main_det = max(160, int(config.get_settings().DET_SIZE))
            if main_det <= SMALL_DET_SIZE:
                self._app_small = self._app
            else:
                try:
                    from insightface.app import FaceAnalysis
                    self._app_small = FaceAnalysis(name=self._model_name)
                    self._app_small.prepare(ctx_id=-1, det_size=(SMALL_DET_SIZE, SMALL_DET_SIZE))
                    logger.info("Detector de pequeno porte carregado (det_size=%d).",
                                SMALL_DET_SIZE)
                except Exception as err:
                    logger.warning("Falha ao criar detector pequeno: %s", err)
                    return None
        return self._app_small

    def is_available(self) -> bool:
        return self._is_loaded and self._app is not None

    def detect_faces(
        self,
        image: np.ndarray,
        min_face_size: int = 40,
        min_det_score: float = 0.40,
    ) -> List[DetectedFace]:
        """Detect faces in a BGR image and compute 512-d normalized embeddings.

        Args:
            image: OpenCV BGR image (np.ndarray).
            min_face_size: Minimum face width/height in pixels to accept.
            min_det_score: Minimum detection confidence (0-1) to accept.

        Returns:
            List of DetectedFace with bbox, embedding, score, and cropped face.
        """
        if not self._is_loaded or self._app is None:
            if not self.load():
                logger.error("FaceEngine não está carregado.")
                return []

        if image is None or getattr(image, "size", 0) == 0:
            return []

        # Small inputs (tight crops) need the small-scale detector.
        h, w = image.shape[:2]
        app = self._app
        if min(h, w) < SMALL_IMAGE_MIN_SIDE:
            small = self._small_detector()
            if small is not None:
                app = small

        try:
            faces = app.get(image)
        except Exception as e:
            logger.error("Erro na inferência do InsightFace: %s", e)
            return []

        results: List[DetectedFace] = []

        for face in faces:
            bbox = face.bbox.tolist()  # [x1, y1, x2, y2]
            det_score = float(face.det_score)

            x1, y1, x2, y2 = [int(v) for v in bbox]
            face_w = x2 - x1
            face_h = y2 - y1

            if det_score < min_det_score:
                continue
            if face_w < min_face_size or face_h < min_face_size:
                continue

            embedding = face.normed_embedding
            if embedding is None:
                continue

            cx1, cy1 = max(0, x1), max(0, y1)
            cx2, cy2 = min(w, x2), min(h, y2)
            if cx2 <= cx1 or cy2 <= cy1:
                continue

            face_img = image[cy1:cy2, cx1:cx2].copy()
            kps = face.kps.tolist() if getattr(face, "kps", None) is not None else None

            results.append(DetectedFace(
                bbox=bbox,
                embedding=embedding,
                det_score=det_score,
                face_image=face_img,
                kps=kps,
            ))

        return results


# Module-level singleton
face_engine = FaceEngine()
