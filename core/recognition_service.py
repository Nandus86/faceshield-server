"""Unified face recognition pipeline used by every ingestion source.

Flow per detected face:
1. Match against the in-memory FaceCache (all registered people).
   - Known + outside cooldown  -> verification log + embedding EMA update + presence.
   - Known + inside cooldown   -> presence only (deduplicated logging).
2. Unknown -> accumulate in PendingSightings; register a new Person only after
   MIN_SIGHTINGS confirmed sightings spaced apart in time (quality-gated),
   guaranteeing each person is registered exactly once.

All database mutation happens under an asyncio lock, so concurrent sources
(RTSP threads, browser webcam, API uploads) can never double-register.
"""

import asyncio
import base64
import datetime
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np
from sqlalchemy import select, desc

import config
from core.database import as_utc, session_scope
from core.events import event_bus
from core.face_cache import FaceCache, face_cache
from core.face_engine import DetectedFace, face_engine
from core.liveness import check_occlusion_and_integrity
from core.models import AppSettings, Event, EventPresence, Person, VerificationLog
from core.notification_service import notification_service
from core.presence_service import touch_presence

logger = logging.getLogger(__name__)

# Minimum seconds between two counted sightings of the same unknown face,
# ensuring confirmation comes from distinct moments (not one burst of frames).
SIGHTING_MIN_GAP_SECONDS = 0.3


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


@dataclass
class RuntimeConfig:
    """Snapshot of runtime settings read once per processing batch."""
    cooldown_minutes: int = 60
    similarity_threshold: float = 0.45
    min_sightings: int = 2
    auto_register_enabled: bool = True


@dataclass
class FaceOutcome:
    """Result of processing a single detected face."""
    status: str                     # known | known_cooldown | registered | pending | unknown
    person_id: Optional[int]
    display_name: str
    confidence: float
    bbox: List[float]
    source: str
    face_b64: Optional[str] = None


@dataclass(eq=False)
class PendingSighting:
    """An unknown face awaiting confirmation before registration."""
    embedding: np.ndarray
    count: int = 1
    first_seen: float = field(default_factory=time.monotonic)
    last_update: float = field(default_factory=time.monotonic)
    best_face_image: Optional[np.ndarray] = None
    best_det_score: float = 0.0


async def load_runtime_config(session) -> RuntimeConfig:
    """Read runtime settings from the DB row, falling back to env config."""
    result = await session.execute(select(AppSettings).where(AppSettings.id == 1))
    st = result.scalar_one_or_none()
    cfg = config.get_settings()
    if st is None:
        return RuntimeConfig(
            cooldown_minutes=cfg.COOLDOWN_MINUTES,
            similarity_threshold=cfg.SIMILARITY_THRESHOLD,
            min_sightings=cfg.MIN_SIGHTINGS,
            auto_register_enabled=True,
        )
    return RuntimeConfig(
        cooldown_minutes=st.cooldown_minutes,
        similarity_threshold=st.similarity_threshold,
        min_sightings=max(1, st.min_sightings),
        auto_register_enabled=bool(st.auto_register_enabled),
    )


class RecognitionService:
    """Single entry point: feed it frames, it keeps the database consistent."""

    def __init__(self, engine=face_engine, cache: FaceCache = face_cache):
        self._engine = engine
        self._cache = cache
        self._lock = asyncio.Lock()
        self._pending: List[PendingSighting] = []
        self._cooldown_cache: dict[int, datetime.datetime] = {}

    # ── Public API ────────────────────────────────────────────

    async def reload_cache(self) -> None:
        """Refresh the in-memory cache from the database."""
        async with session_scope() as session:
            result = await session.execute(select(Person))
            self._cache.load_from_rows(result.scalars().all())

    async def process_image(
        self,
        image: np.ndarray,
        source: str = "api",
        return_images: bool = False,
        min_face_size: Optional[int] = None,
        min_det_score: Optional[float] = None,
    ) -> List[FaceOutcome]:
        """Detect faces in an image and run the full recognition pipeline."""
        if image is None or getattr(image, "size", 0) == 0:
            return []

        cfg_min_size = min_face_size or config.get_settings().MIN_FACE_SIZE
        cfg_min_score = min_det_score or config.get_settings().MIN_DET_SCORE

        loop = asyncio.get_running_loop()
        try:
            detected: List[DetectedFace] = await loop.run_in_executor(
                None,
                lambda: self._engine.detect_faces(
                    image, min_face_size=cfg_min_size, min_det_score=cfg_min_score
                ),
            )
        except Exception:
            logger.exception("Falha na detecção facial (%s).", source)
            return []

        if not detected:
            return []

        async with self._lock:
            return await self._process_detected(image, detected, source, return_images)

    # ── Pipeline ──────────────────────────────────────────────

    async def _process_detected(self, image, detected, source, return_images):
        outcomes: List[FaceOutcome] = []

        async with session_scope() as session:
            rt = await load_runtime_config(session)
            self._purge_expired_pending()

            active_event_id = await self._active_event_id(session)

            for face in detected:
                face_b64 = self._encode_face(face) if return_images else None
                is_occluded, _ = check_occlusion_and_integrity(
                    face.face_image, face.bbox, getattr(face, "kps", None)
                )

                # Occluded/covered faces require tighter distance and margin to avoid false positive matches
                match_thresh = min(rt.similarity_threshold, 0.32) if is_occluded else rt.similarity_threshold
                match_margin = 0.06 if is_occluded else 0.04

                person_id, distance = self._cache.match(face.embedding, match_thresh, min_margin=match_margin)

                if person_id is not None:
                    outcome = await self._handle_known(
                        session, person_id, distance, face, source, rt, active_event_id, is_occluded=is_occluded
                    )
                elif rt.auto_register_enabled and not is_occluded:
                    outcome = await self._handle_unknown(face, source, rt)
                else:
                    outcome = FaceOutcome(
                        status="unknown",
                        person_id=None,
                        display_name="Desconhecido",
                        confidence=self._confidence(rt.similarity_threshold),
                        bbox=[round(v, 1) for v in face.bbox],
                        source=source,
                    )

                outcome.face_b64 = face_b64
                outcomes.append(outcome)

        return outcomes

    @staticmethod
    async def _active_event_id(session) -> Optional[int]:
        result = await session.execute(
            select(Event.id).where(Event.ended_at.is_(None)).order_by(Event.started_at.desc()).limit(1)
        )
        row = result.scalar_one_or_none()
        return int(row) if row is not None else None

    async def _handle_known(self, session, person_id, distance, face, source, rt,
                            active_event_id=None, is_occluded: bool = False) -> FaceOutcome:
        result = await session.execute(select(Person).where(Person.id == person_id))
        person = result.scalar_one_or_none()

        if person is None:
            self._cache.remove(person_id)
            return FaceOutcome(
                status="unknown",
                person_id=None,
                display_name="Desconhecido",
                confidence=self._confidence(distance),
                bbox=[round(v, 1) for v in face.bbox],
                source=source,
            )

        confidence = self._confidence(distance)
        display = person.display_name
        bbox = [round(v, 1) for v in face.bbox]

        person.sighting_count = (person.sighting_count or 0) + 1

        # Only update embedding if match is pristine (high confidence), face is high quality, and not occluded
        if not is_occluded and distance <= 0.28 and getattr(face, "det_score", 0.0) >= 0.75:
            await self._maybe_update_embedding(session, person, face.embedding, alpha=0.02)

        await touch_presence(session, person.id, source)

        in_cooldown = await self._in_cooldown_cached(session, person.id, rt.cooldown_minutes)
        if not in_cooldown:
            already_in_event = False
            if active_event_id is not None:
                result = await session.execute(
                    select(EventPresence).where(
                        EventPresence.event_id == active_event_id,
                        EventPresence.person_id == person.id,
                    )
                )
                already_in_event = result.scalar_one_or_none() is not None

            if not already_in_event:
                frame_path = await self._save_frame_async(face.face_image)
                session.add(VerificationLog(
                    person_id=person.id,
                    confidence=confidence,
                    frame_image_path=str(frame_path) if frame_path else None,
                    source=source,
                ))
                if active_event_id is not None:
                    session.add(EventPresence(
                        event_id=active_event_id,
                        person_id=person.id,
                        face_image_path=str(frame_path) if frame_path else None,
                    ))
                status = "known"
                self._cooldown_cache[person.id] = _now()
                logger.info("Reconhecido: %s (conf=%.2f, fonte=%s)", display, confidence, source)
                await notification_service.notify("person_recognized", {
                    "person_id": person.id,
                    "name": display,
                    "confidence": round(confidence, 3),
                    "source": source,
                })
            else:
                status = "known_cooldown"
        else:
            status = "known_cooldown"

        await event_bus.publish_async("recognition", {
            "person_id": person.id,
            "name": display,
            "status": status,
            "confidence": round(confidence, 3),
            "source": source,
        })

        return FaceOutcome(status=status, person_id=person.id, display_name=display,
                           confidence=confidence, bbox=bbox, source=source)

    async def _handle_unknown(self, face, source, rt) -> FaceOutcome:
        entry = self._match_pending(face.embedding, rt.similarity_threshold)

        if entry is not None:
            now = time.monotonic()
            if now - entry.last_update >= SIGHTING_MIN_GAP_SECONDS:
                entry.count += 1
                entry.last_update = now
            if face.det_score > entry.best_det_score:
                entry.best_det_score = face.det_score
                entry.best_face_image = face.face_image

            if entry.count < max(1, rt.min_sightings):
                return FaceOutcome(
                    status="pending", person_id=None, display_name="Desconhecido",
                    confidence=self._confidence(rt.similarity_threshold),
                    bbox=[round(v, 1) for v in face.bbox], source=source,
                )

            # Confirmed stranger: register exactly once.
            self._pending = [p for p in self._pending if p is not entry]
            best_image = entry.best_face_image if entry.best_face_image is not None else face.face_image
            return await self._register_person(best_image, entry.embedding, source)

        self._pending.append(PendingSighting(
            embedding=np.array(face.embedding, dtype=np.float32),
            best_face_image=face.face_image,
            best_det_score=face.det_score,
        ))
        return FaceOutcome(
            status="pending", person_id=None, display_name="Desconhecido",
            confidence=self._confidence(rt.similarity_threshold),
            bbox=[round(v, 1) for v in face.bbox], source=source,
        )

    async def _register_person(self, face_image: np.ndarray, embedding: np.ndarray,
                               source: str) -> FaceOutcome:
        image_path = await self._save_registration_async(face_image)

        vec = np.asarray(embedding, dtype=np.float32).reshape(-1)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm

        async with session_scope() as session:
            person = Person(
                embedding=vec.tolist(),
                face_image_path=str(image_path) if image_path else None,
                sighting_count=1,
            )
            session.add(person)
            await session.flush()

            session.add(VerificationLog(
                person_id=person.id,
                confidence=1.0,
                frame_image_path=str(image_path) if image_path else None,
                source=source,
                is_new_registration=True,
            ))
            await touch_presence(session, person.id, source)

            active_event_id = await self._active_event_id(session)
            if active_event_id is not None:
                session.add(EventPresence(
                    event_id=active_event_id,
                    person_id=person.id,
                    face_image_path=str(image_path) if image_path else None,
                ))

            display = person.display_name
            person_id = person.id

        self._cache.add(person_id, vec)

        logger.info("Nova pessoa registrada automaticamente: %s (fonte=%s)", display, source)
        await event_bus.publish_async("person_registered", {
            "person_id": person_id,
            "name": display,
            "source": source,
        })
        await notification_service.notify("person_registered", {
            "person_id": person_id,
            "name": display,
            "source": source,
        })

        return FaceOutcome(status="registered", person_id=person_id, display_name=display,
                           confidence=1.0, bbox=[], source=source)

    # ── Helpers ───────────────────────────────────────────────

    def _match_pending(self, embedding: np.ndarray, threshold: float) -> Optional[PendingSighting]:
        vec = np.asarray(embedding, dtype=np.float32).reshape(-1)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        best_entry, best_dist = None, float("inf")
        for entry in self._pending:
            dist = float(1.0 - np.clip(float(np.dot(entry.embedding, vec)), -1.0, 1.0))
            if dist < best_dist:
                best_dist, best_entry = dist, entry
        if best_entry is not None and best_dist <= threshold:
            return best_entry
        return None

    def _purge_expired_pending(self) -> None:
        ttl_seconds = config.get_settings().SIGHTING_TTL_MINUTES * 60
        cutoff = time.monotonic() - ttl_seconds
        self._pending = [e for e in self._pending if e.last_update >= cutoff]

    @staticmethod
    def _confidence(distance: float) -> float:
        return float(round(max(0.0, min(1.0, 1.0 - distance)), 3))

    async def _in_cooldown_cached(self, session, person_id: int, cooldown_minutes: int) -> bool:
        """Return True if person was logged within the cooldown window.

        Caches the last log timestamp in memory so subsequent frames avoid a
        database round-trip (the common case while a person stays on screen).
        """
        if cooldown_minutes <= 0:
            return False
        cached = self._cooldown_cache.get(person_id)
        if cached is not None:
            return cached >= _now() - datetime.timedelta(minutes=cooldown_minutes)

        result = await session.execute(
            select(VerificationLog.detected_at)
            .where(VerificationLog.person_id == person_id)
            .order_by(desc(VerificationLog.detected_at))
            .limit(1)
        )
        last = result.scalar_one_or_none()
        last_dt = as_utc(last) if last is not None else None
        if last_dt is not None:
            self._cooldown_cache[person_id] = last_dt
        return last_dt is not None and (
            last_dt >= _now() - datetime.timedelta(minutes=cooldown_minutes)
        )

    @staticmethod
    async def _maybe_update_embedding(session, person: Person, new_embedding: np.ndarray,
                                      alpha: float = 0.02) -> None:
        """Exponential running average makes profiles robust to angle/lighting drift without risk of corruption."""
        try:
            old = np.asarray(person.embedding, dtype=np.float32).reshape(-1)
            blended = (1.0 - alpha) * old + alpha * np.asarray(new_embedding, dtype=np.float32)
            norm = np.linalg.norm(blended)
            if norm > 0:
                blended = blended / norm
            person.embedding = blended.tolist()
            face_cache.update(person.id, blended)
        except Exception as err:
            logger.warning("Falha ao atualizar embedding de person_id=%s: %s", person.id, err)

    @staticmethod
    def _encode_face(face: DetectedFace) -> Optional[str]:
        try:
            ok, buffer = cv2.imencode(".jpg", face.face_image, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ok:
                return f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"
        except Exception:
            pass
        return None

    @staticmethod
    async def _save_frame_async(face_image: np.ndarray) -> Optional[Path]:
        return await asyncio.get_running_loop().run_in_executor(
            None, RecognitionService._save_image_sync, config.FRAMES_DIR, face_image, "frame"
        )

    @staticmethod
    async def _save_registration_async(face_image: np.ndarray) -> Optional[Path]:
        return await asyncio.get_running_loop().run_in_executor(
            None, RecognitionService._save_image_sync, config.FACES_DIR, face_image, "face"
        )

    @staticmethod
    def _save_image_sync(directory: str, image: np.ndarray, prefix: str) -> Optional[Path]:
        try:
            directory_path = Path(directory)
            directory_path.mkdir(parents=True, exist_ok=True)
            path = directory_path / f"{prefix}_{uuid.uuid4().hex}.jpg"
            cv2.imwrite(str(path), image)
            return path
        except Exception as err:
            logger.warning("Falha ao salvar imagem '%s': %s", prefix, err)
            return None

    # Test hook: replace detector implementation.
    def set_detector(self, detector) -> None:
        self._engine = detector


# Module-level singleton
recognition_service = RecognitionService()
