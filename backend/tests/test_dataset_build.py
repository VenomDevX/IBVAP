"""Tests for the dataset rebuild pipeline (ml/dataset_build/* and ml/grouping)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml.grouping import family, group_key, stable_bucket  # noqa: E402

# ──────────────────────────────────────────────────────────────
# ml.grouping — leak-safe grouping keys
# ──────────────────────────────────────────────────────────────


def test_group_key_strips_roboflow_hash():
    a = group_key("frame_001_jpg.rf.abc123def456.jpg")
    b = group_key("frame_001_jpg.rf.999888777666.jpg")
    assert a == b, "roboflow twins must share a group"
    assert a == "frame_001"


def test_group_key_strips_clip_frame_number():
    # our own convert_mot17_to_yolo naming: mot_<clip>_<frame>.jpg
    a = group_key("mot_02_000123.jpg")
    b = group_key("mot_02_000124.jpg")
    assert a == b == "mot_02", "frames of one clip must share a group"


def test_group_key_separates_different_clips():
    assert group_key("mot_02_000123.jpg") != group_key("mot_04_000123.jpg")


def test_group_key_leaves_plain_names_alone():
    # a non-clip, non-roboflow name keeps its identity (minus extension)
    assert group_key("aircraft_9931.jpg") == "aircraft_9931"


def test_family_groups_by_leading_alpha_prefix():
    assert family("mot_02_000123.jpg") == "mot"
    assert family("virat_01_000001.jpg") == "virat"
    assert family("1234.jpg") == "misc"


def test_stable_bucket_is_deterministic():
    assert stable_bucket("abc", 42) == stable_bucket("abc", 42)
    assert 0.0 <= stable_bucket("abc", 42) < 1.0


def test_stable_bucket_varies_with_seed():
    assert stable_bucket("abc", 42) != stable_bucket("abc", 43)
