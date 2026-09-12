"""build_dataset.py — rebuild backend/data into a clean data/dataset/.

Six resumable stages. Re-running skips completed stages; --force <stage>
re-runs that stage and everything after it.

  1 index       scan sources, md5 + dHash              (~17 min, 8 workers)
  2 dedup       exact + near duplicates, BEFORE split  (~10 s)
  3 rebalance   pick ~50k detector images, rare kept   (~2 min)
  4 restructure class plan: aggregates, prune, fold    (~10 s)
  5 split       group-aware leak-free train/val        (~10 s)
  6 emit        copy files, write configs, verify      (~20-40 min)

NON-DESTRUCTIVE: never modifies or deletes anything under data/raw_dataset/.
Use scripts/cleanup_data.py for that, and only after training has succeeded.

Usage:
  python scripts/build_dataset.py
  python scripts/build_dataset.py --target-detector 40000
  python scripts/build_dataset.py --force rebalance
  python scripts/build_dataset.py --dry-run          # plan only, copy nothing
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ml.dataset_build import dedup as dedup_mod  # noqa: E402
from ml.dataset_build import emit as emit_mod  # noqa: E402
from ml.dataset_build import rebalance as rebal_mod  # noqa: E402
from ml.dataset_build import restructure as restruct_mod  # noqa: E402
from ml.dataset_build import split as split_mod  # noqa: E402
from ml.dataset_build.index import (  # noqa: E402
    has_label_file,
    read_index,
    read_label_classes,
    scan_tree,
    write_index,
)
from ml.taxonomy import COARSE_NAMES  # noqa: E402

STAGES = ["index", "dedup", "rebalance", "restructure", "split", "emit"]
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw_dataset"   # untouched source imagery
OUT = DATA / "dataset"       # the built release
BUILD = OUT / ".build"


def done(stage: str) -> bool:
    return (BUILD / f"{stage}.done").exists()


def mark(stage: str) -> None:
    BUILD.mkdir(parents=True, exist_ok=True)
    (BUILD / f"{stage}.done").write_text(time.strftime("%Y-%m-%d %H:%M:%S"))


def clear_from(stage: str) -> None:
    for s in STAGES[STAGES.index(stage) :]:
        (BUILD / f"{s}.done").unlink(missing_ok=True)


def _hms(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"


def main() -> None:
    ap = argparse.ArgumentParser(description="Rebuild backend/data into data/dataset/")
    ap.add_argument("--target-detector", type=int, default=50000)
    ap.add_argument("--threshold", type=int, default=200,
                    help="min unique images for a fine class to survive")
    ap.add_argument("--cap", type=int, default=1500, help="max images per class")
    ap.add_argument("--background-frac", type=float, default=0.05)
    ap.add_argument("--val-fraction", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--workers", type=int, default=8,
                    help="index workers; 8 measured fastest, 16 regresses on IO")
    ap.add_argument("--force", choices=STAGES, help="re-run this stage and all after it")
    ap.add_argument("--dry-run", action="store_true",
                    help="run stages 1-5 and report; skip the copy in stage 6")
    args = ap.parse_args()

    if args.force:
        clear_from(args.force)
    BUILD.mkdir(parents=True, exist_ok=True)

    mpath = OUT / "manifest.json"
    manifest: dict = {}
    if mpath.exists():
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
    manifest["config"] = vars(args) | {"generated": time.strftime("%Y-%m-%d %H:%M:%S")}

    def save() -> None:
        mpath.parent.mkdir(parents=True, exist_ok=True)
        mpath.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    t_all = time.time()

    # ───────────────── 1. index ─────────────────
    det_idx, crop_idx = BUILD / "index_detector.jsonl", BUILD / "index_crops.jsonl"
    if not done("index"):
        t = time.time()
        print("[1/6] index — hashing every source image (slow, once)")
        n1 = write_index(
            scan_tree(RAW / "detector_yolo", "detector", args.workers, progress=20000),
            det_idx,
        )
        print(f"      detector: {n1:,}")
        n2 = write_index(
            scan_tree(RAW / "cropped_classes", "crops", args.workers, progress=50000),
            crop_idx,
        )
        print(f"      crops:    {n2:,}")
        manifest["index"] = {"detector": n1, "crops": n2, "seconds": round(time.time() - t)}
        save()
        mark("index")
    print(f"[1/6] index       OK  ({manifest.get('index', {}).get('detector', '?')} det, "
          f"{manifest.get('index', {}).get('crops', '?')} crops)")

    # ───────────────── 2. dedup ─────────────────
    # Detector and crops are handled one at a time and freed between, and
    # removals stream straight to disk. Holding 677k records plus a ~365k-entry
    # removal list plus the label dict at once got this process OOM-killed.
    dd, dc = BUILD / "dedup_detector.jsonl", BUILD / "dedup_crops.jsonl"
    if not done("dedup"):
        t = time.time()
        counts: dict[str, int] = {"conflict": 0}
        with open(BUILD / "duplicates.jsonl", "w", encoding="utf-8") as fh:

            def emit(dropped: str, kept: str, reason: str) -> None:
                counts[reason] = counts.get(reason, 0) + 1
                fh.write(
                    json.dumps({"dropped": dropped, "kept": kept, "reason": reason}) + "\n"
                )

            # Tie-breaks decide which copy of a duplicate SURVIVES, and getting
            # them wrong silently destroys whole classes — see the docstrings on
            # restructure.specificity and rebalance.rare_first_priority.
            print("      detector: reading labels for rare-class dedup priority...")
            det = read_index(det_idx)
            n_det_in = len(det)
            det_labels = {r.path: read_label_classes(r.path) for r in det}
            before = sum(counts.values())
            det_k, _ = dedup_mod.dedup(
                det,
                priority=rebal_mod.rare_first_priority(det_labels),
                on_removed=emit,
            )
            det_removed = sum(counts.values()) - before
            write_index(det_k, dd)
            n_det_out = len(det_k)
            del det, det_labels, det_k
            gc.collect()

            print("      crops: deduping per class...")
            crops = read_index(crop_idx)
            n_crop_in = len(crops)
            before = sum(counts.values())
            crop_k, _ = dedup_mod.dedup(
                crops,
                priority=restruct_mod.specificity,
                group_by=restruct_mod.dedup_group,
                conflict_key=restruct_mod.dedup_group,
                on_removed=emit,
            )
            crop_removed = sum(counts.values()) - before
            write_index(crop_k, dc)
            n_crop_out = len(crop_k)
            del crops, crop_k
            gc.collect()

        manifest["dedup"] = {
            "detector_in": n_det_in, "detector_kept": n_det_out,
            "detector_removed": det_removed,
            "crops_in": n_crop_in, "crops_kept": n_crop_out,
            "crops_removed": crop_removed,
            "crops_removed_pct": round(100 * crop_removed / max(1, n_crop_in), 2),
            "label_conflicts": counts.get("conflict", 0),
            "by_reason": counts,
            "seconds": round(time.time() - t),
        }
        save()
        mark("dedup")
    m = manifest["dedup"]
    print(f"[2/6] dedup       OK  detector {m['detector_in']:,} -> {m['detector_kept']:,}   "
          f"crops {m['crops_in']:,} -> {m['crops_kept']:,} (-{m['crops_removed_pct']}%)")
    if m.get("label_conflicts"):
        print(f"      {m['label_conflicts']:,} images dropped as LABEL CONFLICTS "
              f"(identical bytes filed under two different classes)")

    # ───────────────── 3. rebalance ─────────────────
    sel_path = BUILD / "detector_selected.jsonl"
    if not done("rebalance"):
        t = time.time()
        det = read_index(dd)
        print("      reading labels...")
        labels = {r.path: read_label_classes(r.path) for r in det}
        labelled = {r.path for r in det if has_label_file(r.path)}
        print(f"      {len(labelled):,}/{len(det):,} have a label file")
        sel, stats = rebal_mod.select_detector_images(
            det, labels, target=args.target_detector,
            background_frac=args.background_frac, seed=args.seed, labelled=labelled,
        )
        write_index(sel, sel_path)
        stats["seconds"] = round(time.time() - t)
        manifest["rebalance"] = stats
        save()
        mark("rebalance")
        del det, labels, labelled, sel
        gc.collect()
    st = manifest["rebalance"]
    print(f"[3/6] rebalance   OK  {st['n_selected']:,} images "
          f"(rare {st['n_rare_kept']:,}, bg {st['background_pct']}%, "
          f"dropped-unlabelled {st['n_dropped_unlabelled']:,})")

    # ───────────────── 4. restructure ─────────────────
    plan_path = BUILD / "class_plan.json"
    if not done("restructure"):
        crops = read_index(dc)
        plan = restruct_mod.build_class_plan(
            crops, threshold=args.threshold, cap=args.cap, seed=args.seed
        )
        plan_path.write_text(
            json.dumps({
                "assignments": plan.assignments, "classes": plan.classes,
                "folded": plan.folded, "dropped": plan.dropped, "counts": plan.counts,
            }),
            encoding="utf-8",
        )
        manifest["restructure"] = {
            "n_classes": len(plan.classes), "classes": plan.classes,
            "counts": plan.counts, "folded": plan.folded, "dropped": plan.dropped,
        }
        save()
        mark("restructure")
        del crops, plan
        gc.collect()
    raw = json.loads(plan_path.read_text(encoding="utf-8"))
    plan = restruct_mod.ClassPlan(**raw)
    print(f"[4/6] restructure OK  {len(plan.classes)} classes, "
          f"{len(plan.folded)} folded, {len(plan.dropped)} dropped")

    # ───────────────── 5. split ─────────────────
    if not done("split"):
        sel = read_index(sel_path)
        d_tr, d_va = split_mod.split_records(sel, args.val_fraction, args.seed)
        split_mod.assert_no_leak(d_tr, d_va)
        del sel
        crops = read_index(dc)
        c_recs = [r for r in crops if r.path in plan.assignments]
        del crops
        gc.collect()
        c_tr, c_va = split_mod.split_records(c_recs, args.val_fraction, args.seed)
        split_mod.assert_no_leak(c_tr, c_va)
        for name, recs in (("det_train", d_tr), ("det_val", d_va),
                           ("cls_train", c_tr), ("cls_val", c_va)):
            write_index(recs, BUILD / f"{name}.jsonl")
        manifest["split"] = {"det_train": len(d_tr), "det_val": len(d_va),
                             "cls_train": len(c_tr), "cls_val": len(c_va)}
        del d_tr, d_va, c_tr, c_va, c_recs
        gc.collect()
        save()
        mark("split")
    sp = manifest["split"]
    print(f"[5/6] split       OK  detector {sp['det_train']:,}/{sp['det_val']:,}   "
          f"classifier {sp['cls_train']:,}/{sp['cls_val']:,}")

    d_tr = read_index(BUILD / "det_train.jsonl")
    d_va = read_index(BUILD / "det_val.jsonl")
    c_tr = read_index(BUILD / "cls_train.jsonl")
    c_va = read_index(BUILD / "cls_val.jsonl")

    if args.dry_run:
        print("\n--dry-run: stopping before the copy. Class list:")
        for c in plan.classes:
            print(f"    {plan.counts[c]:>6,}  {c}")
        save()
        return

    # ───────────────── 6. emit ─────────────────
    if not done("emit"):
        t = time.time()
        print("[6/6] emit — copying detector images...")
        ds = emit_mod.emit_detector(d_tr, d_va, OUT, progress=10000)
        print("      copying classifier crops...")
        cs = emit_mod.emit_classifier(plan, c_tr, c_va, OUT, progress=10000)

        # Remove anything an earlier build left behind. Resumable copies skip
        # same-size destinations, so stale output survives into the new tree and
        # verify() cannot spot it — those files carry valid labels too.
        print("      pruning stale files from earlier builds...")
        expected = {
            "detector/images/train": {Path(r.path).name for r in d_tr},
            "detector/images/val": {Path(r.path).name for r in d_va},
            "detector/labels/train": {Path(r.path).with_suffix(".txt").name for r in d_tr},
            "detector/labels/val": {Path(r.path).with_suffix(".txt").name for r in d_va},
            "classifier/train/": set(plan.classes),
            "classifier/val/": set(plan.classes),
        }
        for split, recs in (("train", c_tr), ("val", c_va)):
            for r in recs:
                cls = plan.assignments.get(r.path)
                if cls:
                    expected.setdefault(f"classifier/{split}/{cls}", set()).add(
                        Path(r.path).name
                    )
        pruned = emit_mod.prune_unexpected(OUT, expected)
        if any(pruned.values()):
            print(f"      pruned {pruned['images']:,} images, {pruned['labels']:,} labels, "
                  f"{pruned['dirs']} stale class folders")

        emit_mod.write_dataset_yaml(OUT)
        (OUT / "classes.json").write_text(
            json.dumps({"coarse": COARSE_NAMES, "fine": plan.classes}, indent=2),
            encoding="utf-8",
        )
        print("      verifying...")
        problems = emit_mod.verify(OUT, expected_counts={
            "detector/images/train": len(d_tr),
            "detector/images/val": len(d_va),
            "detector/labels/train": len(d_tr),
            "detector/labels/val": len(d_va),
        })
        if problems:
            for p in problems[:20]:
                print("      PROBLEM:", p)
            raise SystemExit(f"verification failed with {len(problems)} problem(s)")
        manifest["emit"] = {"detector": ds, "classifier": cs,
                            "seconds": round(time.time() - t)}
        save()
        mark("emit")
    print("[6/6] emit        OK  verified")

    print(f"\nDataset ready in {_hms(time.time() - t_all)} at {OUT}")
    print(f"  detector yaml : {OUT / 'detector' / 'dataset.yaml'}")
    print(f"  classes       : {OUT / 'classes.json'}")
    print(f"  manifest      : {mpath}")
    print("\nNext:  python scripts/train_yolo.py --benchmark")


if __name__ == "__main__":
    # Windows spawn: the ProcessPoolExecutor in stage 1 re-imports this module
    # in each worker, so the guard is required, not decorative.
    os.environ.setdefault("PYTHONUTF8", "1")
    main()
