"""Tests for the stage-2 fine-grained classifier and its pipeline wiring."""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.classification.fine_classifier import (  # noqa: E402
    MILITARY_TYPES,
    FineClassifier,
)
from src.classification.preprocess import preprocess_crop  # noqa: E402
from src.tracking.track import Track  # noqa: E402


def _crop(h=120, w=90, colour=(30, 60, 90)):
    img = np.zeros((h, w, 3), np.uint8)
    img[:, :] = colour
    return img


# ──────────────────────────────────────────────────────────────
# Graceful degradation — the pipeline must run without stage 2
# ──────────────────────────────────────────────────────────────


def test_disabled_when_weights_missing(tmp_path):
    c = FineClassifier(enabled=True, weights=str(tmp_path / "nope.pt"))
    assert c.active is False
    assert c.classify(_crop()) is None


def test_disabled_when_explicitly_off():
    c = FineClassifier(enabled=False)
    assert c.active is False
    assert c.classify(_crop()) is None


def test_inactive_classifier_never_raises_on_bad_input():
    """The pipeline calls this every few seconds per track; it must not throw."""
    c = FineClassifier(enabled=False)
    for bad in (None, np.zeros((0, 0, 3), np.uint8)):
        assert c.classify(bad) is None


# ──────────────────────────────────────────────────────────────
# Class gating — military crops only
# ──────────────────────────────────────────────────────────────


def test_military_types_matches_taxonomy():
    from ml.taxonomy import MILITARY_TYPES as TAXONOMY_MILITARY

    assert MILITARY_TYPES == frozenset(TAXONOMY_MILITARY)


def test_is_military_gates_correctly():
    for t in ("aircraft", "helicopter", "drone_uav", "military_ground_vehicle"):
        assert FineClassifier.is_military(t) is True
    for t in ("person", "car", "bus", "license_plate", "animal", "bicycle"):
        assert FineClassifier.is_military(t) is False


# ──────────────────────────────────────────────────────────────
# Preprocessing — must match the training transform exactly
# ──────────────────────────────────────────────────────────────


def test_preprocess_shape_and_dtype():
    out = preprocess_crop(_crop(), 224)
    assert out.shape == (3, 224, 224)
    assert out.dtype == np.float32


def test_preprocess_matches_the_training_transform_exactly():
    """Serving and training must agree bit-for-bit. A drift here does not raise,
    it silently costs accuracy — so it is asserted, not assumed."""
    from PIL import Image
    from torchvision import transforms

    ref_tf = transforms.Compose([
        transforms.Resize(int(224 * 1.14)),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225)),
    ])
    rng = np.random.default_rng(0)
    for h, w in ((300, 400), (90, 120), (224, 224)):
        rgb = rng.integers(0, 255, (h, w, 3), dtype=np.uint8)
        ref = ref_tf(Image.fromarray(rgb)).numpy()
        mine = preprocess_crop(rgb[:, :, ::-1].copy(), 224)  # BGR in
        assert np.abs(ref - mine).max() < 1e-6


def test_preprocess_converts_bgr_to_rgb():
    """Without the swap every prediction runs on colour-inverted input."""
    red_bgr = np.zeros((100, 100, 3), np.uint8)
    red_bgr[:, :, 2] = 255  # red in BGR
    out = preprocess_crop(red_bgr, 224)
    # after RGB conversion + ImageNet normalisation, channel 0 (R) dominates
    assert out[0].mean() > out[1].mean()
    assert out[0].mean() > out[2].mean()


def test_preprocess_handles_a_tiny_distant_crop():
    """Far-away aircraft produce small crops; they must still get an answer."""
    assert preprocess_crop(_crop(8, 6), 224).shape == (3, 224, 224)


def test_preprocess_rejects_empty():
    with pytest.raises(ValueError):
        preprocess_crop(np.zeros((0, 0, 3), np.uint8), 224)


# ──────────────────────────────────────────────────────────────
# Track carries the result through to the API
# ──────────────────────────────────────────────────────────────


def test_track_defaults_to_unknown_fine_type():
    t = Track(track_id=1, object_type="aircraft", camera_id="CAM_1", bbox=(0, 0, 10, 10), confidence=0.9)
    assert t.fine_type == "unknown"
    assert t.fine_confidence == 0.0


def test_track_to_dict_exposes_fine_type():
    t = Track(track_id=1, object_type="aircraft", camera_id="CAM_1", bbox=(0, 0, 10, 10), confidence=0.9)
    t.fine_type = "F16"
    t.fine_confidence = 0.8123
    d = t.to_dict()
    assert d["fine_type"] == "F16"
    assert d["fine_confidence"] == 0.812
