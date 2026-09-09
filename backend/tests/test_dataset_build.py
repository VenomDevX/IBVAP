"""Tests for the dataset rebuild pipeline (ml/dataset_build/* and ml/grouping)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from ml.dataset_build.index import (  # noqa: E402
    dhash,
    has_label_file,
    label_path_for,
    read_index,
    read_label_classes,
    scan_tree,
    walk_images,
    write_index,
)
from ml.grouping import family, group_key, stable_bucket  # noqa: E402


def _img(path, size=(32, 32), color=(10, 20, 30)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


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


# ──────────────────────────────────────────────────────────────
# Stage 1 — index
# ──────────────────────────────────────────────────────────────


def test_dhash_identical_images_match(tmp_path):
    a = _img(tmp_path / "a.jpg")
    b = _img(tmp_path / "b.jpg")
    assert dhash(a) == dhash(b)


def test_dhash_differs_for_different_images(tmp_path):
    a = _img(tmp_path / "a.jpg", color=(0, 0, 0))
    b = tmp_path / "b.jpg"
    # dHash compares each pixel to its RIGHT neighbour, so the gradient must run
    # horizontally to register. linear_gradient is vertical, hence the rotate:
    # a vertical gradient has constant rows and hashes to 0, same as solid black.
    Image.linear_gradient("L").rotate(90).convert("RGB").save(b)
    assert dhash(a) != dhash(b)


def test_dhash_ignores_a_vertical_gradient_by_design(tmp_path):
    """Documents a real limitation: dHash is blind to purely vertical structure."""
    flat = _img(tmp_path / "flat.jpg", color=(0, 0, 0))
    vert = tmp_path / "vert.jpg"
    Image.linear_gradient("L").convert("RGB").save(vert)
    assert dhash(flat) == dhash(vert) == 0


def test_dhash_is_64_bits(tmp_path):
    a = _img(tmp_path / "a.jpg")
    assert 0 <= dhash(a) < (1 << 64)


def test_label_path_for_swaps_images_dir_for_labels(tmp_path):
    p = tmp_path / "images" / "train" / "x.jpg"
    assert label_path_for(str(p)) == tmp_path / "labels" / "train" / "x.txt"


def test_read_label_classes(tmp_path):
    img = _img(tmp_path / "images" / "train" / "x.jpg")
    lbl = tmp_path / "labels" / "train" / "x.txt"
    lbl.parent.mkdir(parents=True, exist_ok=True)
    lbl.write_text("0 0.5 0.5 0.1 0.1\n7 0.2 0.2 0.1 0.1\n0 0.3 0.3 0.1 0.1\n")
    assert read_label_classes(str(img)) == [0, 7, 0]


def test_read_label_classes_missing_file_is_empty(tmp_path):
    img = _img(tmp_path / "images" / "train" / "y.jpg")
    assert read_label_classes(str(img)) == []


def test_read_label_classes_empty_file_is_background(tmp_path):
    img = _img(tmp_path / "images" / "train" / "z.jpg")
    lbl = tmp_path / "labels" / "train" / "z.txt"
    lbl.parent.mkdir(parents=True, exist_ok=True)
    lbl.write_text("")
    assert read_label_classes(str(img)) == []


def test_scan_tree_records_dimensions_and_hashes(tmp_path):
    _img(tmp_path / "images" / "train" / "a.jpg", size=(64, 48))
    recs = list(scan_tree(tmp_path, "detector"))
    assert len(recs) == 1
    r = recs[0]
    assert r.width == 64 and r.height == 48
    assert len(r.md5) == 32
    assert r.source == "detector"
    assert r.rel == "images/train/a.jpg"


def test_scan_tree_skips_non_images(tmp_path):
    _img(tmp_path / "a.jpg")
    (tmp_path / "notes.txt").write_text("not an image")
    assert len(list(scan_tree(tmp_path, "crops"))) == 1


def test_scan_tree_skips_corrupt_images(tmp_path):
    _img(tmp_path / "good.jpg")
    (tmp_path / "bad.jpg").write_bytes(b"this is not a jpeg")
    recs = list(scan_tree(tmp_path, "crops"))
    assert [r.rel for r in recs] == ["good.jpg"]


def test_index_roundtrip(tmp_path):
    _img(tmp_path / "images" / "train" / "a.jpg")
    recs = list(scan_tree(tmp_path, "detector", workers=1))
    out = tmp_path / "index.jsonl"
    assert write_index(recs, out) == 1
    assert read_index(out) == recs


def test_has_label_file_distinguishes_empty_from_missing(tmp_path):
    """An empty label is a background negative; a missing one is a lost
    annotation. detector_yolo has 846 of the latter in images/valid alone, and
    training on them as background teaches the model to ignore real objects."""
    bg = _img(tmp_path / "images" / "train" / "bg.jpg")
    lost = _img(tmp_path / "images" / "train" / "lost.jpg")
    lbl = tmp_path / "labels" / "train" / "bg.txt"
    lbl.parent.mkdir(parents=True, exist_ok=True)
    lbl.write_text("")

    assert has_label_file(str(bg)) is True
    assert has_label_file(str(lost)) is False
    # read_label_classes cannot tell them apart — that is why has_label_file exists
    assert read_label_classes(str(bg)) == read_label_classes(str(lost)) == []


def test_scan_tree_parallel_matches_serial(tmp_path):
    for i in range(12):
        _img(tmp_path / f"i{i}.jpg", size=(16 + i, 16), color=(i * 5, 40, 90))
    serial = sorted(scan_tree(tmp_path, "crops", workers=1), key=lambda r: r.rel)
    parallel = sorted(scan_tree(tmp_path, "crops", workers=4), key=lambda r: r.rel)
    assert serial == parallel


def test_scan_tree_records_true_size_not_draft_size(tmp_path):
    """draft() rescales the decoder; width/height must be the real dimensions."""
    _img(tmp_path / "big.jpg", size=(640, 480))
    (rec,) = list(scan_tree(tmp_path, "crops", workers=1))
    assert (rec.width, rec.height) == (640, 480)


def test_walk_images_finds_nested_files(tmp_path):
    _img(tmp_path / "a" / "b" / "c" / "deep.jpg")
    _img(tmp_path / "top.jpg")
    found = {os.path.basename(p) for p in walk_images(tmp_path)}
    assert found == {"deep.jpg", "top.jpg"}
