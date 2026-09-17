"""Tests for the FaceCache (in-memory embedding matching)."""

import numpy as np
import pytest

from core.face_cache import FaceCache


def make_vec(seed: float, size: int = 512) -> np.ndarray:
    rng = np.random.default_rng(int(abs(seed) * 1000))
    vec = rng.standard_normal(size).astype(np.float32)
    return vec / np.linalg.norm(vec)


class TestFaceCache:
    def test_empty_cache_matches_nothing(self):
        cache = FaceCache()
        person_id, distance = cache.match(make_vec(1.0), threshold=0.65)
        assert person_id is None
        assert distance == 1.0

    def test_exact_match_found(self):
        cache = FaceCache()
        vec = make_vec(42.0)
        cache.add(7, vec, name="Alice")

        found, distance = cache.match(vec, threshold=0.65)
        assert found == 7
        assert distance < 0.01

    def test_similar_vector_matches(self):
        cache = FaceCache()
        base = make_vec(1.0)
        noisy = base + np.random.default_rng(5).standard_normal(512).astype(np.float32) * 0.05
        noisy /= np.linalg.norm(noisy)
        cache.add(3, base)

        found, distance = cache.match(noisy, threshold=0.4)
        assert found == 3
        assert distance < 0.4

    def test_different_vector_rejected(self):
        cache = FaceCache()
        cache.add(1, make_vec(10.0))

        found, distance = cache.match(make_vec(500.0), threshold=0.65)
        assert found is None
        assert distance > 0.65

    def test_update_changes_embedding(self):
        cache = FaceCache()
        old_vec = make_vec(2.0)
        new_vec = make_vec(3.0)
        cache.add(9, old_vec)
        cache.update(9, new_vec)

        found_old, _ = cache.match(old_vec, threshold=0.2)
        found_new, _ = cache.match(new_vec, threshold=0.2)
        assert found_old is None
        assert found_new == 9

    def test_remove_deletes_person(self):
        cache = FaceCache()
        vec = make_vec(8.0)
        cache.add(4, vec)
        cache.remove(4)

        assert cache.count() == 0
        found, _ = cache.match(vec, threshold=0.1)
        assert found is None

    def test_add_existing_id_updates(self):
        cache = FaceCache()
        v1, v2 = make_vec(11.0), make_vec(12.0)
        cache.add(2, v1)
        cache.add(2, v2)

        assert cache.count() == 1
        found, _ = cache.match(v2, threshold=0.1)
        assert found == 2

    def test_rename(self):
        cache = FaceCache()
        cache.add(6, make_vec(13.0), name="Bob")
        cache.rename(6, "Bobby")
        assert cache.get_name(6) == "Bobby"
        assert cache.display_name(99) == "Pessoa #99"

    def test_zero_vector_ignored(self):
        cache = FaceCache()
        cache.add(5, make_vec(21.0))
        found, _ = cache.match(np.zeros(512, dtype=np.float32), threshold=0.9)
        assert found is None

    def test_ambiguous_match_rejected(self):
        """When a vector is almost equidistant between 2 people and distance > 0.28, reject as ambiguous."""
        cache = FaceCache()
        v1 = make_vec(100.0)
        v2 = make_vec(200.0)
        cache.add(1, v1, name="Alice")
        cache.add(2, v2, name="Bob")

        # Blend v1 and v2 equally to create an ambiguous vector between them
        blended = (v1 + v2) / np.linalg.norm(v1 + v2)
        found, dist = cache.match(blended, threshold=0.60, min_margin=0.04)
        assert found is None

    def test_unambiguous_match_accepted(self):
        """When one candidate is clearly closer than all others, accept match."""
        cache = FaceCache()
        v1 = make_vec(100.0)
        v2 = make_vec(200.0)
        cache.add(1, v1, name="Alice")
        cache.add(2, v2, name="Bob")

        # Slightly perturbed version of v1
        noisy_v1 = v1 + np.random.default_rng(1).standard_normal(512).astype(np.float32) * 0.03
        noisy_v1 /= np.linalg.norm(noisy_v1)

        found, dist = cache.match(noisy_v1, threshold=0.45)
        assert found == 1
        assert dist < 0.25

