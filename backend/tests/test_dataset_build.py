"""Tests for the dataset rebuild pipeline (ml/dataset_build/* and ml/grouping)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from ml.dataset_build.dedup import dedup, hamming  # noqa: E402
from ml.dataset_build.index import (  # noqa: E402
    ImageRecord,
    dhash,
    has_label_file,
    label_path_for,
    read_index,
    read_label_classes,
    scan_tree,
    walk_images,
    write_index,
)
from ml.dataset_build.rebalance import (  # noqa: E402
    RARE_CLASS_IDS,
    select_detector_images,
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


# ──────────────────────────────────────────────────────────────
# Stage 2 — dedup
# ──────────────────────────────────────────────────────────────


def _rec(path, md5="m", dh=0, w=100, h=100, source="crops"):
    return ImageRecord(
        path=path, source=source, rel=path, width=w, height=h,
        size=w * h, md5=md5, dhash=dh,
    )


def test_hamming():
    assert hamming(0b0000, 0b0000) == 0
    assert hamming(0b0001, 0b0000) == 1
    assert hamming(0b1011, 0b0010) == 2


def test_dedup_removes_exact_duplicates():
    kept, removed = dedup([_rec("a.jpg", "same"), _rec("b.jpg", "same")])
    assert len(kept) == 1
    assert [r[2] for r in removed] == ["exact"]


def test_dedup_keeps_highest_resolution_representative():
    kept, _ = dedup([
        _rec("small.jpg", "m1", 1, w=50, h=50),
        _rec("big.jpg", "m2", 1, w=500, h=500),
    ])
    assert [r.path for r in kept] == ["big.jpg"]


def test_dedup_removes_near_duplicates_within_threshold():
    kept, removed = dedup([_rec("a.jpg", "m1", 0b1100), _rec("b.jpg", "m2", 0b0000)])
    assert len(kept) == 1
    assert removed[0][2] == "near"


def test_dedup_keeps_images_beyond_threshold():
    kept, _ = dedup([_rec("a.jpg", "m1", 0b1111), _rec("b.jpg", "m2", 0b0000)])
    assert len(kept) == 2


def test_dedup_near_boundary_is_inclusive_at_three():
    # exactly 3 differing bits -> duplicate; 4 -> distinct
    three = dedup([_rec("a", "m1", 0b111), _rec("b", "m2", 0)])[0]
    four = dedup([_rec("a", "m1", 0b1111), _rec("b", "m2", 0)])[0]
    assert len(three) == 1
    assert len(four) == 2


def test_dedup_finds_near_dupes_across_all_four_bands():
    """Pigeonhole check: a difference in the top band must still be caught."""
    base = 0
    for band in range(4):
        other = 1 << (band * 16)  # single differing bit, one per band
        kept, _ = dedup([_rec("a", "m1", base), _rec("b", "m2", other)])
        assert len(kept) == 1, f"missed a near-dupe differing in band {band}"


def test_dedup_disabled_when_max_distance_zero():
    kept, _ = dedup([_rec("a", "m1", 0b1), _rec("b", "m2", 0b0)], max_distance=0)
    assert len(kept) == 2


def test_dedup_is_deterministic_regardless_of_input_order():
    recs = [_rec(f"{i}.jpg", f"m{i}", i * 7) for i in range(60)]
    a, _ = dedup(list(recs))
    b, _ = dedup(list(reversed(recs)))
    assert {r.path for r in a} == {r.path for r in b}


def test_dedup_removed_entries_point_at_a_survivor():
    recs = [_rec(f"{i}.jpg", "same", 0) for i in range(5)]
    kept, removed = dedup(recs)
    survivors = {r.path for r in kept}
    assert all(keeper in survivors for _, keeper, _ in removed)


# ──────────────────────────────────────────────────────────────
# Stage 3 — detector rebalance
# ──────────────────────────────────────────────────────────────


def _d(path, w=640, h=640):
    return ImageRecord(path=path, source="detector", rel=path, width=w, height=h,
                       size=w * h, md5=path, dhash=0)


def test_rare_class_ids_match_the_scarce_classes():
    # military_ground_vehicle 7, bus 2, helicopter 9, motorcycle 4,
    # truck 3, bicycle 5, drone_uav 10, animal 12
    assert RARE_CLASS_IDS == frozenset({7, 2, 9, 4, 3, 5, 10, 12})


def test_every_rare_image_is_kept_even_when_over_target():
    recs = [_d(f"rare{i}.jpg") for i in range(100)]
    labels = {r.path: [7] for r in recs}
    sel, stats = select_detector_images(recs, labels, target=10, background_frac=0.0)
    assert len(sel) == 100, "rare-class images must never be dropped"
    assert stats["n_rare_kept"] == 100


def test_person_only_images_are_subsampled_but_rare_survives():
    rare = [_d("rare.jpg")]
    person = [_d(f"p{i}.jpg") for i in range(1000)]
    labels = {"rare.jpg": [7]}
    labels.update({r.path: [0] for r in person})
    sel, _ = select_detector_images(rare + person, labels, target=101,
                                    background_frac=0.0)
    assert len(sel) == 101
    assert "rare.jpg" in {r.path for r in sel}


def test_common_selection_prefers_images_with_more_boxes():
    many = _d("many.jpg")
    few = _d("few.jpg")
    labels = {"many.jpg": [0, 0, 0, 1], "few.jpg": [0]}
    sel, _ = select_detector_images([few, many], labels, target=1,
                                    background_frac=0.0)
    assert [r.path for r in sel] == ["many.jpg"]


def test_backgrounds_capped_at_fraction_of_final_set():
    common = [_d(f"c{i}.jpg") for i in range(95)]
    empty = [_d(f"e{i}.jpg") for i in range(500)]
    labels = {r.path: [0] for r in common}
    labels.update({r.path: [] for r in empty})
    sel, stats = select_detector_images(common + empty, labels, target=95,
                                        background_frac=0.05)
    n_empty = sum(1 for r in sel if not labels[r.path])
    assert n_empty > 0, "some background is wanted, just not 14.7%"
    assert stats["background_pct"] <= 5.5
    assert n_empty == stats["n_background_kept"]


def test_unlabelled_images_are_dropped_not_treated_as_background():
    good = _d("good.jpg")
    lost = _d("lost.jpg")   # no label FILE — annotation lost, not a background
    labels = {"good.jpg": [0], "lost.jpg": []}
    sel, stats = select_detector_images([good, lost], labels, target=10,
                                        background_frac=0.5,
                                        labelled={"good.jpg"})
    assert [r.path for r in sel] == ["good.jpg"]
    assert stats["n_dropped_unlabelled"] == 1


def test_selection_is_deterministic_regardless_of_order():
    recs = [_d(f"p{i}.jpg") for i in range(200)]
    labels = {r.path: [0] for r in recs}
    a, _ = select_detector_images(recs, labels, target=50, seed=42)
    b, _ = select_detector_images(list(reversed(recs)), labels, target=50, seed=42)
    assert {r.path for r in a} == {r.path for r in b}


def test_stats_reports_per_class_box_counts():
    recs = [_d("a.jpg"), _d("b.jpg")]
    labels = {"a.jpg": [0, 0, 7], "b.jpg": [2]}
    _, stats = select_detector_images(recs, labels, target=10, background_frac=0.0)
    assert stats["boxes_per_class"] == {0: 2, 2: 1, 7: 1}
