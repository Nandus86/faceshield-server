"""Unit tests for passive liveness and quality checking."""

import numpy as np
import pytest
from core.liveness import check_liveness_and_quality, check_occlusion_and_integrity


def test_empty_or_zero_image():
    passed, score, reason = check_liveness_and_quality(None, [0, 0, 10, 10])
    assert not passed
    assert score == 0.0

    passed, score, reason = check_liveness_and_quality(np.zeros((0, 0, 3), dtype=np.uint8), [0, 0, 0, 0])
    assert not passed


def test_too_small_crop():
    small = np.ones((10, 10, 3), dtype=np.uint8) * 100
    passed, score, reason = check_liveness_and_quality(small, [0, 0, 10, 10])
    assert not passed
    assert "pequeno" in reason.lower()


def test_abnormal_aspect_ratio():
    weird = np.ones((100, 20, 3), dtype=np.uint8) * 100
    passed, score, reason = check_liveness_and_quality(weird, [0, 0, 20, 100])
    assert not passed
    assert "proporção" in reason.lower()


def test_uniform_blank_crop():
    blank = np.ones((60, 60, 3), dtype=np.uint8) * 128
    passed, score, reason = check_liveness_and_quality(blank, [0, 0, 60, 60])
    assert not passed


def test_valid_textured_image():
    # Textured gradient image with high frequency detail
    img = np.random.randint(0, 256, (80, 80, 3), dtype=np.uint8)
    passed, score, reason = check_liveness_and_quality(img, [0, 0, 80, 80], min_sharpness=20.0)
    assert passed
    assert score > 0.0
    assert reason == "Aprovado"


def test_occlusion_collapsed_mouth_landmarks():
    img = np.random.randint(50, 200, (100, 100, 3), dtype=np.uint8)
    # kps: left_eye, right_eye, nose, left_mouth, right_mouth
    kps_collapsed = [
        [30.0, 30.0],  # left eye
        [70.0, 30.0],  # right eye (eye_dist = 40)
        [50.0, 50.0],  # nose
        [50.0, 75.0],  # left mouth
        [51.0, 75.0],  # right mouth (mouth_dist = 1.0 < 0.12 * 40)
    ]
    is_occluded, reason = check_occlusion_and_integrity(img, [0, 0, 100, 100], kps_collapsed)
    assert is_occluded
    assert "colapsados" in reason.lower()


def test_occlusion_inverted_mouth_landmarks():
    img = np.random.randint(50, 200, (100, 100, 3), dtype=np.uint8)
    # mouth center placed above nose
    kps_inverted = [
        [30.0, 30.0],
        [70.0, 30.0],
        [50.0, 50.0],  # nose at y=50
        [35.0, 45.0],  # mouth at y=45 (above nose!)
        [65.0, 45.0],
    ]
    is_occluded, reason = check_occlusion_and_integrity(img, [0, 0, 100, 100], kps_inverted)
    assert is_occluded
    assert "inválido" in reason.lower()

