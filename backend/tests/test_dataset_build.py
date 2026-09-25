"""Tests for the dataset rebuild pipeline (ml/dataset_build/* and ml/grouping)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from PIL import Image  # noqa: E402

from ml.dataset_build.dedup import dedup, hamming  # noqa: E402
from ml.dataset_build.emit import (  # noqa: E402
    emit_detector,
    prune_unexpected,
    verify,
    write_dataset_yaml,
)
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
    rare_first_priority,
    select_detector_images,
)
from ml.dataset_build.restructure import (  # noqa: E402
    AGGREGATE_MAP,
    build_class_plan,
    canonical_class_name,
    coarse_parent,
    dedup_group,
    leaf_of,
    specificity,
)
from ml.dataset_build.split import assert_no_leak, split_records  # noqa: E402
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
        path=path,
        source=source,
        rel=path,
        width=w,
        height=h,
        size=w * h,
        md5=md5,
        dhash=dh,
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
    kept, _ = dedup(
        [
            _rec("small.jpg", "m1", 1, w=50, h=50),
            _rec("big.jpg", "m2", 1, w=500, h=500),
        ]
    )
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
    return ImageRecord(path=path, source="detector", rel=path, width=w, height=h, size=w * h, md5=path, dhash=0)


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
    sel, _ = select_detector_images(rare + person, labels, target=101, background_frac=0.0)
    assert len(sel) == 101
    assert "rare.jpg" in {r.path for r in sel}


def test_common_selection_prefers_images_with_more_boxes():
    many = _d("many.jpg")
    few = _d("few.jpg")
    labels = {"many.jpg": [0, 0, 0, 1], "few.jpg": [0]}
    sel, _ = select_detector_images([few, many], labels, target=1, background_frac=0.0)
    assert [r.path for r in sel] == ["many.jpg"]


def test_backgrounds_capped_at_fraction_of_final_set():
    common = [_d(f"c{i}.jpg") for i in range(95)]
    empty = [_d(f"e{i}.jpg") for i in range(500)]
    labels = {r.path: [0] for r in common}
    labels.update({r.path: [] for r in empty})
    sel, stats = select_detector_images(common + empty, labels, target=95, background_frac=0.05)
    n_empty = sum(1 for r in sel if not labels[r.path])
    assert n_empty > 0, "some background is wanted, just not 14.7%"
    assert stats["background_pct"] <= 5.5
    assert n_empty == stats["n_background_kept"]


def test_unlabelled_images_are_dropped_not_treated_as_background():
    good = _d("good.jpg")
    lost = _d("lost.jpg")  # no label FILE — annotation lost, not a background
    labels = {"good.jpg": [0], "lost.jpg": []}
    sel, stats = select_detector_images([good, lost], labels, target=10, background_frac=0.5, labelled={"good.jpg"})
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


# ──────────────────────────────────────────────────────────────
# Stage 4 — classifier restructure
# ──────────────────────────────────────────────────────────────


def _c(rel, i, w=100):
    p = f"{rel}/{i}.jpg"
    return ImageRecord(path=p, source="crops", rel=p, width=w, height=w, size=w * w, md5=p, dhash=i)


def test_aggregate_map_drops_only_the_ambiguous_one():
    assert AGGREGATE_MAP["Military_Aircraft"] == "aircraft"
    assert AGGREGATE_MAP["Animal"] == "animal"
    assert AGGREGATE_MAP["Two_Wheeler"] is None


def test_leaf_of_reads_the_parent_folder():
    assert leaf_of("Military/F16/x.jpg") == "F16"
    assert leaf_of("Military_Aircraft/x.jpg") == "Military_Aircraft"
    assert leaf_of("x.jpg") is None


def test_canonical_name_folds_disk_and_taxonomy_spelling():
    # folder is Night_Vision_Object, taxonomy says "Night Vision Object"
    assert canonical_class_name("Night_Vision_Object") == "Night_Vision_Object"
    assert canonical_class_name("Night Vision Object") == "Night_Vision_Object"
    assert canonical_class_name("F16") == "F16"
    assert canonical_class_name("NotARealClass") is None


def test_coarse_parent_mapping():
    assert coarse_parent("F16") == "aircraft"
    assert coarse_parent("AH64") == "helicopter"
    assert coarse_parent("MQ9") == "drone_uav"
    assert coarse_parent("Tank") == "military_ground_vehicle"
    assert coarse_parent("Dog") == "animal"


def test_class_above_threshold_survives():
    recs = [_c("Military/F16", i) for i in range(250)]
    plan = build_class_plan(recs, threshold=200)
    assert "F16" in plan.classes
    assert plan.counts["F16"] == 250


def test_starved_siblings_pool_into_a_viable_coarse_bucket():
    """The real case: AH64 125, Mi24 120, Ka52 92 each fail the floor alone,
    but together they make a `helicopter` bucket worth training."""
    recs = [_c("Military/AH64", i) for i in range(125)]
    recs += [_c("Military/Mi24", i) for i in range(120)]
    recs += [_c("Military/Ka52", i) for i in range(92)]
    plan = build_class_plan(recs, threshold=200)

    assert plan.classes == ["helicopter"]
    for fine in ("AH64", "Mi24", "Ka52"):
        assert fine not in plan.classes
        assert plan.folded[fine] == "helicopter"
    assert plan.assignments["Military/AH64/0.jpg"] == "helicopter"
    assert plan.counts["helicopter"] == 337


def test_a_lone_starved_class_is_dropped_when_its_bucket_stays_short():
    """Folding is not a free pass: if the bucket is still under the floor it goes.
    Here Mi24 survives on its own, so it never joins helicopter to rescue AH64."""
    recs = [_c("Military/AH64", i) for i in range(50)]
    recs += [_c("Military/Mi24", i) for i in range(200)]
    plan = build_class_plan(recs, threshold=200)

    assert plan.classes == ["Mi24"]
    assert plan.folded["AH64"] == "helicopter"
    assert plan.dropped["helicopter"] == 50
    assert "Military/AH64/0.jpg" not in plan.assignments


def test_two_wheeler_images_are_dropped_entirely():
    recs = [_c("Two_Wheeler", i) for i in range(500)]
    recs += [_c("Vehicles/Bicycle", i) for i in range(300)]
    plan = build_class_plan(recs, threshold=200)
    assert "Two_Wheeler" not in plan.classes
    assert plan.dropped["Two_Wheeler"] == 500
    assert not any(k.startswith("Two_Wheeler/") for k in plan.assignments)
    assert "Bicycle" in plan.classes, "the unambiguous sibling must be unaffected"


def test_military_aircraft_aggregate_becomes_the_aircraft_bucket():
    recs = [_c("Military_Aircraft", i) for i in range(300)]
    plan = build_class_plan(recs, threshold=200)
    assert plan.assignments["Military_Aircraft/0.jpg"] == "aircraft"
    assert "aircraft" in plan.classes


def test_generic_jet_merges_into_aircraft_not_its_own_class():
    """Generic_Jet means 'a jet we could not identify' - that IS the bucket."""
    recs = [_c("Military/Generic_Jet", i) for i in range(400)]
    plan = build_class_plan(recs, threshold=200)
    assert "Generic_Jet" not in plan.classes
    assert plan.assignments["Military/Generic_Jet/0.jpg"] == "aircraft"


def test_unknown_folder_is_dropped_and_recorded():
    recs = [_c("Weird/Nonsense", i) for i in range(300)]
    plan = build_class_plan(recs, threshold=200)
    assert plan.classes == []
    assert plan.dropped["<unknown:Nonsense>"] == 300


def test_cap_limits_class_size_preferring_large_images():
    recs = [_c("People/Person", i, w=10 + i) for i in range(300)]
    plan = build_class_plan(recs, threshold=10, cap=100)
    assigned = [k for k, v in plan.assignments.items() if v == "Person"]
    assert len(assigned) == 100
    assert "People/Person/299.jpg" in assigned  # largest kept
    assert "People/Person/0.jpg" not in assigned  # smallest dropped
    assert plan.counts["Person"] == 100


def test_starved_class_with_no_parent_capacity_is_dropped():
    # 5 AH64 only: folds to helicopter, which is still under threshold -> dropped
    recs = [_c("Military/AH64", i) for i in range(5)]
    plan = build_class_plan(recs, threshold=200)
    assert plan.classes == []
    assert plan.dropped["helicopter"] == 5


def test_plan_is_deterministic_regardless_of_order():
    recs = [_c("Military/F16", i) for i in range(400)]
    a = build_class_plan(list(recs), threshold=200, cap=250)
    b = build_class_plan(list(reversed(recs)), threshold=200, cap=250)
    assert a.assignments == b.assignments
    assert a.classes == b.classes


# ──────────────────────────────────────────────────────────────
# Stage 5 — group-aware split
# ──────────────────────────────────────────────────────────────


def _s(name):
    return ImageRecord(path=f"/d/{name}", source="detector", rel=name, width=64, height=64, size=100, md5=name, dhash=0)


def test_split_is_roughly_val_fraction():
    recs = [_s(f"img_{i}.jpg") for i in range(1000)]
    train, val = split_records(recs, val_fraction=0.1)
    assert 50 < len(val) < 200
    assert len(train) + len(val) == 1000


def test_split_keeps_clip_frames_together():
    recs = [_s(f"mot_02_{i:06d}.jpg") for i in range(50)]
    recs += [_s(f"mot_09_{i:06d}.jpg") for i in range(50)]
    train, val = split_records(recs, val_fraction=0.5)
    assert_no_leak(train, val)


def test_split_keeps_roboflow_twins_together():
    recs = [_s(f"frame_1_jpg.rf.{i:012x}.jpg") for i in range(20)]
    recs += [_s(f"other_9_jpg.rf.{i:012x}.jpg") for i in range(20)]
    train, val = split_records(recs, val_fraction=0.5)
    assert_no_leak(train, val)


def test_assert_no_leak_detects_a_leak():
    a = [_s("mot_02_000001.jpg")]
    b = [_s("mot_02_000002.jpg")]  # same clip -> same group
    with pytest.raises(AssertionError):
        assert_no_leak(a, b)


def test_every_family_is_represented_in_val():
    # one family whose single group might otherwise hash into train
    recs = [_s("solo_000001.jpg")]
    train, val = split_records(recs, val_fraction=0.1)
    assert len(val) == 1 and len(train) == 0


def test_split_is_deterministic():
    recs = [_s(f"img_{i}.jpg") for i in range(500)]
    _, v1 = split_records(recs, seed=42)
    _, v2 = split_records(list(reversed(recs)), seed=42)
    assert {r.path for r in v1} == {r.path for r in v2}


# ──────────────────────────────────────────────────────────────
# Stage 6 — emit + verify
# ──────────────────────────────────────────────────────────────


def _make_det(tmp_path, name, classes):
    img = tmp_path / "src" / "images" / "train" / name
    img.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (32, 32)).save(img)
    lbl = tmp_path / "src" / "labels" / "train" / Path(name).with_suffix(".txt").name
    lbl.parent.mkdir(parents=True, exist_ok=True)
    lbl.write_text("".join(f"{c} 0.5 0.5 0.1 0.1\n" for c in classes))
    return ImageRecord(
        path=str(img), source="detector", rel=f"images/train/{name}", width=32, height=32, size=100, md5=name, dhash=0
    )


def test_emit_detector_copies_images_and_labels(tmp_path):
    tr = [_make_det(tmp_path, "a.jpg", [0])]
    va = [_make_det(tmp_path, "b.jpg", [7])]
    out = tmp_path / "dataset"
    stats = emit_detector(tr, va, out)
    assert (out / "detector" / "images" / "train" / "a.jpg").exists()
    assert (out / "detector" / "labels" / "train" / "a.txt").exists()
    assert (out / "detector" / "images" / "val" / "b.jpg").exists()
    assert stats["train"] == 1 and stats["val"] == 1 and stats["no_label"] == 0


def test_emit_is_resumable(tmp_path):
    tr = [_make_det(tmp_path, "a.jpg", [0])]
    out = tmp_path / "dataset"
    emit_detector(tr, [], out)
    stats = emit_detector(tr, [], out)  # second run skips the existing file
    assert stats["skipped"] == 1 and stats["copied"] == 0


def test_write_dataset_yaml_has_13_classes(tmp_path):
    text = write_dataset_yaml(tmp_path).read_text(encoding="utf-8")
    assert "nc: 13" in text
    assert "6: license_plate" in text
    assert "7: military_ground_vehicle" in text


def test_verify_flags_missing_label(tmp_path):
    out = tmp_path / "dataset"
    emit_detector([_make_det(tmp_path, "a.jpg", [0])], [], out)
    (out / "detector" / "labels" / "train" / "a.txt").unlink()
    assert any("missing label" in p for p in verify(out))


def test_verify_flags_out_of_range_class(tmp_path):
    out = tmp_path / "dataset"
    emit_detector([_make_det(tmp_path, "a.jpg", [99])], [], out)
    assert any("out of range" in p for p in verify(out))


def test_verify_flags_same_image_in_both_splits(tmp_path):
    rec = _make_det(tmp_path, "dup.jpg", [0])
    out = tmp_path / "dataset"
    emit_detector([rec], [rec], out)
    assert any("both train and val" in p for p in verify(out))


def test_verify_clean_dataset_returns_no_problems(tmp_path):
    tr = [_make_det(tmp_path, "a.jpg", [0])]
    va = [_make_det(tmp_path, "b.jpg", [7])]
    out = tmp_path / "dataset"
    emit_detector(tr, va, out)
    write_dataset_yaml(out)
    assert verify(out) == []


# ──────────────────────────────────────────────────────────────
# CLI orchestrator
# ──────────────────────────────────────────────────────────────


def test_build_dataset_cli_help_runs():
    import subprocess

    r = subprocess.run(
        [sys.executable, "scripts/build_dataset.py", "--help"],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    assert r.returncode == 0, r.stderr
    for flag in ("--target-detector", "--threshold", "--cap", "--force", "--dry-run"):
        assert flag in r.stdout


# ──────────────────────────────────────────────────────────────
# Regression: dedup tie-breaks must not annihilate specific classes
# ──────────────────────────────────────────────────────────────


def _agg(rel, md5, dh=None):
    """A crop record at `rel` with a given md5 (byte-identical copies share one).

    dhash defaults to a value derived from md5 so identical bytes hash alike and
    unrelated fixtures do not collide in the near pass.
    """
    return ImageRecord(
        path=rel,
        source="crops",
        rel=rel,
        width=100,
        height=100,
        size=1000,
        md5=md5,
        dhash=dh if dh is not None else (hash(md5) & 0xFFFFFFFFFFFFFFFF),
    )


def test_specificity_ranks_specific_class_over_aggregate():
    assert specificity(_agg("Vehicles/Bicycle/x.jpg", "m")) == 1
    assert specificity(_agg("Two_Wheeler/x.jpg", "m")) == 0
    assert specificity(_agg("Animals/Dog/x.jpg", "m")) == 1
    assert specificity(_agg("Animal/x.jpg", "m")) == 0
    assert specificity(_agg("Military/F16/x.jpg", "m")) == 1
    assert specificity(_agg("Military_Aircraft/x.jpg", "m")) == 0


def test_dedup_keeps_the_specifically_labelled_copy_not_the_aggregate():
    """THE regression. Two_Wheeler/ holds byte-identical copies of Bicycle/ and
    Motorcycle/; Animal/ of Dog/ etc. Ranking on path alone kept the aggregate
    (T < V, 'Animal/' < 'Animals') and zeroed 8 real classes."""
    recs = [
        _agg("Two_Wheeler/a.jpg", "m1"),
        _agg("Vehicles/Bicycle/a.jpg", "m1"),  # same bytes
        _agg("Animal/b.jpg", "m2"),
        _agg("Animals/Dog/b.jpg", "m2"),  # same bytes
        _agg("Military_Aircraft/c.jpg", "m3"),
        _agg("Military/F16/c.jpg", "m3"),  # same bytes
    ]
    kept, _ = dedup(recs, priority=specificity)
    surviving = {r.rel for r in kept}
    assert surviving == {
        "Vehicles/Bicycle/a.jpg",
        "Animals/Dog/b.jpg",
        "Military/F16/c.jpg",
    }, f"aggregate copy survived instead of the labelled one: {surviving}"


def test_dedup_specificity_survives_a_full_class_plan():
    """End to end: aggregates are exact copies, so the fine classes must live."""
    recs = []
    for i in range(300):
        recs.append(_agg(f"Vehicles/Bicycle/{i}.jpg", f"bike{i}"))
        recs.append(_agg(f"Two_Wheeler/{i}.jpg", f"bike{i}"))  # identical bytes
    kept, _ = dedup(recs, max_distance=0, priority=specificity)
    plan = build_class_plan(kept, threshold=200)
    assert "Bicycle" in plan.classes
    assert plan.counts["Bicycle"] == 300
    assert plan.dropped.get("Two_Wheeler", 0) == 0, "nothing should be left in it"


def test_rare_first_priority_keeps_the_rare_detector_image():
    a = ImageRecord(
        path="person.jpg", source="detector", rel="person.jpg", width=640, height=640, size=100, md5="same", dhash=0
    )
    b = ImageRecord(
        path="tank.jpg", source="detector", rel="tank.jpg", width=640, height=640, size=100, md5="same", dhash=0
    )
    labels = {"person.jpg": [0], "tank.jpg": [7]}  # 7 = military_ground_vehicle
    kept, _ = dedup([a, b], priority=rare_first_priority(labels))
    assert [r.path for r in kept] == ["tank.jpg"]


def test_dedup_group_resolves_aggregates_to_the_target_class():
    assert dedup_group(_agg("Military_Aircraft/x.jpg", "m")) == "aircraft"
    assert dedup_group(_agg("Military/F16/x.jpg", "m")) == "F16"
    assert dedup_group(_agg("Animals/Dog/x.jpg", "m")) == "Dog"
    assert dedup_group(_agg("Two_Wheeler/x.jpg", "m")) == "<dropped>"


def test_near_dedup_does_not_merge_across_classes():
    """An F16 and an F18 that look alike at 8x8 are two labels, not one image.
    Dropping either destroys the distinction the classifier exists to learn."""
    a = _agg("Military/F16/a.jpg", "m1", dh=0b1010)
    b = _agg("Military/F18/b.jpg", "m2", dh=0b1011)  # Hamming 1

    merged, _ = dedup([a, b], max_distance=3)
    assert len(merged) == 1, "sanity: without grouping they collapse"

    kept, _ = dedup([a, b], max_distance=3, group_by=dedup_group)
    assert {r.rel for r in kept} == {"Military/F16/a.jpg", "Military/F18/b.jpg"}


def test_near_dedup_still_merges_within_one_class():
    a = _agg("Military/F16/a.jpg", "m1", dh=0b1010)
    b = _agg("Military/F16/b.jpg", "m2", dh=0b1011)
    kept, removed = dedup([a, b], max_distance=3, group_by=dedup_group)
    assert len(kept) == 1
    assert removed[0][2] == "near"


# ──────────────────────────────────────────────────────────────
# train_classifier — dataset surgery must live in the builder
# ──────────────────────────────────────────────────────────────


def _script(name):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "scripts", name), encoding="utf-8") as fh:
        return fh.read()


def test_train_classifier_help_runs():
    import subprocess

    r = subprocess.run(
        [sys.executable, "scripts/train_classifier.py", "--help"],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    assert r.returncode == 0, r.stderr
    for flag in ("--arch", "--resume", "--epochs", "--batch"):
        assert flag in r.stdout


def test_train_classifier_has_no_dataset_surgery():
    """Flattening, capping and splitting belong to build_dataset.py. Doing them
    at train time is what put duplicate images on both sides of the split."""
    src = _script("train_classifier.py")
    assert "def prepare_dataset" not in src
    assert "max_per_class" not in src
    assert "shutil.copy" not in src


def test_train_classifier_has_no_hardcoded_aggregate_skiplist():
    """The structural fix in restructure.py replaced this band-aid."""
    src = _script("train_classifier.py")
    assert '"Animal", "Military_Aircraft", "Two_Wheeler"' not in src
    assert '("Animal",' not in src


def test_train_classifier_resume_restores_optimizer_and_scheduler():
    """Weights alone are not a resume: without optimizer moments and the LR
    schedule position, continuing mid-cosine restarts at the wrong LR."""
    src = _script("train_classifier.py")
    for key in ('"opt"', '"sched"', '"scaler"', '"epoch"'):
        assert "opt.load_state_dict" in src or key in src
    assert "opt.load_state_dict" in src
    assert "sched.load_state_dict" in src
    assert "scaler.load_state_dict" in src


def test_train_classifier_loads_checkpoints_safely():
    src = _script("train_classifier.py")
    assert "weights_only=True" in src, "torch.load must not allow arbitrary unpickling"


def test_conflicting_labels_on_identical_bytes_drop_both():
    """Every Forklift image is also filed as Car, every Bus image also as Car.
    Resolving that alphabetically could teach the model a forklift is a car."""
    a = _agg("Vehicles/Car/x.jpg", "same")
    b = _agg("Vehicles/Forklift/x.jpg", "same")
    kept, removed = dedup([a, b], conflict_key=dedup_group)
    assert kept == []
    assert {r[2] for r in removed} == {"conflict"}


def test_aggregate_vs_child_is_a_duplicate_not_a_conflict():
    """The aggregate loses on priority before the conflict check, so the
    specifically-labelled child survives rather than both being discarded."""
    agg = _agg("Two_Wheeler/x.jpg", "same")
    child = _agg("Vehicles/Bicycle/x.jpg", "same")
    kept, removed = dedup([agg, child], priority=specificity, conflict_key=dedup_group)
    assert [r.rel for r in kept] == ["Vehicles/Bicycle/x.jpg"]
    assert removed[0][2] == "exact"


def test_same_class_identical_bytes_is_a_plain_duplicate():
    a = _agg("Military/F16/a.jpg", "same")
    b = _agg("Military/F16/b.jpg", "same")
    kept, removed = dedup([a, b], conflict_key=dedup_group)
    assert len(kept) == 1
    assert removed[0][2] == "exact"


def test_prune_removes_stale_output_from_an_earlier_build(tmp_path):
    """Resumable copies skip same-size destinations, so a previous build's files
    survive into the new tree. They carry valid labels, so only the expected set
    can tell them apart."""
    out = tmp_path / "dataset"
    keep = _make_det(tmp_path, "keep.jpg", [0])
    stale = _make_det(tmp_path, "stale.jpg", [0])
    emit_detector([keep, stale], [], out)  # simulate the earlier build
    assert (out / "detector" / "images" / "train" / "stale.jpg").exists()

    expected = {
        "detector/images/train": {"keep.jpg"},
        "detector/labels/train": {"keep.txt"},
    }
    removed = prune_unexpected(out, expected)
    assert removed["images"] == 1 and removed["labels"] == 1
    assert (out / "detector" / "images" / "train" / "keep.jpg").exists()
    assert not (out / "detector" / "images" / "train" / "stale.jpg").exists()


def test_prune_removes_class_folders_no_longer_in_the_plan(tmp_path):
    out = tmp_path / "dataset"
    for cls in ("F16", "Forklift"):
        d = out / "classifier" / "train" / cls
        d.mkdir(parents=True)
        Image.new("RGB", (8, 8)).save(d / "a.jpg")
    removed = prune_unexpected(out, {"classifier/train/": {"F16"}})
    assert removed["dirs"] == 1
    assert (out / "classifier" / "train" / "F16").exists()
    assert not (out / "classifier" / "train" / "Forklift").exists()


def test_verify_flags_a_file_count_mismatch(tmp_path):
    """Per-file checks pass on stale output; only the count betrays it."""
    out = tmp_path / "dataset"
    emit_detector([_make_det(tmp_path, "a.jpg", [0]), _make_det(tmp_path, "b.jpg", [0])], [], out)
    problems = verify(out, expected_counts={"detector/images/train": 1})
    assert any("expected 1" in p and "found 2" in p for p in problems)
    assert verify(out) == [], "without counts the stale file is invisible"
