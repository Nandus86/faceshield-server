"""Tests for the unified recognition pipeline (registration-once guarantees)."""

import asyncio
from types import SimpleNamespace

import numpy as np
import pytest

from core.face_cache import FaceCache
from core.recognition_service import RecognitionService
import core.recognition_service as recognition_module


def make_embedding(seed: float) -> np.ndarray:
    rng = np.random.default_rng(int(abs(seed) * 1000))
    vec = rng.standard_normal(512).astype(np.float32)
    return vec / np.linalg.norm(vec)


def make_face(embedding: np.ndarray, score: float = 0.9) -> SimpleNamespace:
    return SimpleNamespace(
        bbox=[10.0, 10.0, 60.0, 60.0],
        embedding=embedding,
        det_score=score,
        face_image=np.zeros((24, 24, 3), dtype=np.uint8),
    )


class FakeDetector:
    def __init__(self):
        self.faces = []

    def detect_faces(self, image, min_face_size=40, min_det_score=0.40):
        return self.faces


@pytest.fixture()
def service(monkeypatch, tmp_path):
    """Fresh RecognitionService with a fake detector and no sighting gap."""
    monkeypatch.setattr(recognition_module, "SIGHTING_MIN_GAP_SECONDS", 0)
    monkeypatch.setattr(recognition_module, "face_cache", FaceCache())
    monkeypatch.setattr(recognition_module.config, "FACES_DIR", str(tmp_path))
    monkeypatch.setattr(recognition_module.config, "FRAMES_DIR", str(tmp_path))

    detector = FakeDetector()
    svc = RecognitionService(engine=detector, cache=FaceCache())
    # Keep EMA updates pointed at the same cache instance used for matching.
    monkeypatch.setattr(recognition_module, "face_cache", FaceCache())
    svc._cache = recognition_module.face_cache
    svc.set_detector(detector)
    return svc


@pytest.fixture()
def fake_image():
    return np.zeros((100, 100, 3), dtype=np.uint8)


def run(coro):
    return asyncio.run(coro)


class TestRegistrationOnce:
    def test_unknown_registered_after_min_sightings(self, service, fake_image):
        face = make_face(make_embedding(1.0))
        service._engine.faces = [face]

        first = run(service.process_image(fake_image, source="test"))
        assert first[0].status == "pending"

        second = run(service.process_image(fake_image, source="test"))
        assert second[0].status == "registered"
        assert second[0].person_id is not None

        assert recognition_module.face_cache.count() == 1

    def test_third_sighting_does_not_duplicate(self, service, fake_image):
        face = make_face(make_embedding(2.0))
        service._engine.faces = [face]

        statuses = []
        for _ in range(3):
            outcomes = run(service.process_image(fake_image, source="test"))
            statuses.append(outcomes[0].status)

        # Third sighting falls inside the default cooldown window created by
        # the registration log itself.
        assert statuses == ["pending", "registered", "known_cooldown"]

        async def count_persons():
            from sqlalchemy import func, select
            from core.database import session_scope
            from core.models import Person
            async with session_scope() as session:
                result = await session.execute(select(func.count(Person.id)))
                return result.scalar()

        assert run(count_persons()) == 1

    def test_different_people_register_separately(self, service, fake_image):
        alice = make_face(make_embedding(3.0))
        bob = make_face(make_embedding(400.0))

        for face in (alice, bob):
            service._engine.faces = [face]
            run(service.process_image(fake_image, source="test"))

        for face in (alice, bob):
            service._engine.faces = [face]
            outcomes = run(service.process_image(fake_image, source="test"))
            assert outcomes[0].status == "registered"

        async def count_persons():
            from sqlalchemy import func, select
            from core.database import session_scope
            from core.models import Person
            async with session_scope() as session:
                result = await session.execute(select(func.count(Person.id)))
                return result.scalar()

        assert run(count_persons()) == 2

    def test_disabled_auto_registration_never_registers(self, service, fake_image, monkeypatch):
        async def disable():
            from core.database import session_scope
            from core.models import AppSettings
            from sqlalchemy import select
            async with session_scope() as session:
                row = (await session.execute(
                    select(AppSettings).where(AppSettings.id == 1))).scalar_one()
                row.auto_register_enabled = False

        run(disable())
        try:
            face = make_face(make_embedding(5.0))
            service._engine.faces = [face]
            for _ in range(4):
                outcomes = run(service.process_image(fake_image, source="test"))
                assert outcomes[0].status == "unknown"
                assert outcomes[0].person_id is None
        finally:
            async def enable():
                from core.database import session_scope
                from core.models import AppSettings
                from sqlalchemy import select
                async with session_scope() as session:
                    row = (await session.execute(
                        select(AppSettings).where(AppSettings.id == 1))).scalar_one()
                    row.auto_register_enabled = True
            run(enable())

    def test_cooldown_deduplicates_logs(self, service, fake_image):
        face = make_face(make_embedding(6.0))
        service._engine.faces = [face]

        run(service.process_image(fake_image, source="test"))     # pending
        run(service.process_image(fake_image, source="test"))     # registered + log
        third = run(service.process_image(fake_image, source="test"))
        assert third[0].status == "known_cooldown"

        fourth = run(service.process_image(fake_image, source="test"))
        assert fourth[0].status == "known_cooldown"

    def test_known_person_not_reregistered_by_new_crop(self, service, fake_image):
        base = make_embedding(7.0)
        variant = base + np.random.default_rng(99).standard_normal(512).astype(np.float32) * 0.02
        variant /= np.linalg.norm(variant)

        service._engine.faces = [make_face(base)]
        run(service.process_image(fake_image, source="test"))
        run(service.process_image(fake_image, source="test"))

        # Same person, slightly different crop — must stay a single person.
        service._engine.faces = [make_face(variant)]
        outcome = run(service.process_image(fake_image, source="test"))
        assert outcome[0].status in ("known_cooldown", "known")
        assert outcome[0].person_id is not None

        async def count_persons():
            from sqlalchemy import func, select
            from core.database import session_scope
            from core.models import Person
            async with session_scope() as session:
                result = await session.execute(select(func.count(Person.id)))
                return result.scalar()

        assert run(count_persons()) == 1

    def test_occluded_face_rejected_for_marginal_match(self, service, fake_image):
        """Occluded faces must not be matched on loose thresholds."""
        base = make_embedding(50.0)
        # Register person
        service._engine.faces = [make_face(base, score=0.95)]
        run(service.process_image(fake_image, source="test"))
        run(service.process_image(fake_image, source="test"))

        # Create an occluded face with collapsed mouth landmarks and distance ~0.38
        kps_collapsed = [[30.0, 30.0], [70.0, 30.0], [50.0, 50.0], [50.0, 75.0], [51.0, 75.0]]
        marginal_vec = base + np.random.default_rng(2).standard_normal(512).astype(np.float32) * 0.45
        marginal_vec /= np.linalg.norm(marginal_vec)

        occluded_face = make_face(marginal_vec, score=0.85)
        occluded_face.kps = kps_collapsed
        service._engine.faces = [occluded_face]

        outcomes = run(service.process_image(fake_image, source="test"))
        # Must NOT match the registered person due to occlusion stricter threshold
        assert outcomes[0].status == "unknown" or outcomes[0].person_id is None

    def test_embedding_not_updated_on_marginal_match(self, service, fake_image):
        """EMA update must only run on pristine matches (dist <= 0.28, det_score >= 0.75)."""
        from core.database import session_scope
        from core.models import Person
        from sqlalchemy import select

        base = make_embedding(60.0)
        service._engine.faces = [make_face(base, score=0.95)]
        run(service.process_image(fake_image, source="test"))
        run(service.process_image(fake_image, source="test"))

        async def get_db_embedding():
            async with session_scope() as session:
                p = (await session.execute(select(Person).where(Person.id == 1))).scalar_one()
                return np.array(p.embedding, dtype=np.float32)

        orig_embedding = run(get_db_embedding())

        # Marginal match: distance around 0.35 (noise = 0.35)
        marginal_vec = base + np.random.default_rng(3).standard_normal(512).astype(np.float32) * 0.35
        marginal_vec /= np.linalg.norm(marginal_vec)

        service._engine.faces = [make_face(marginal_vec, score=0.65)]  # low det_score
        run(service.process_image(fake_image, source="test"))

        after_embedding = run(get_db_embedding())
        # Embedding must NOT have changed because match was marginal
        np.testing.assert_array_almost_equal(orig_embedding, after_embedding, decimal=5)
