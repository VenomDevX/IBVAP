"""
remap_to_coarse.py — build the coarse detector dataset from the existing merged data
===================================================================================
The original source datasets live on an unmounted J: drive, so instead of re-merging
we RE-LABEL the already-merged `unified_yolo` set:

  unified_yolo (91-class labels)  --FINE_TO_COARSE-->  detector_yolo (13-class labels)

Images are HARD-LINKED (instant, no disk cost on the same NTFS volume); only the small
`.txt` label files are rewritten. `unified_yolo` is left untouched as a backup.

Also cleans labels while remapping:
  * keep only class + 4 bbox fields (drops segmentation polygons)
  * clamp coords to [0, 1]; drop boxes with non-positive w/h or negative coords
  * keep empty label files (legitimate background negatives)

After this, run:
  python scripts/add_plates.py --src "<...v13i.yolov8>" --dst data/raw_dataset/detector_yolo --purge-old --limit 18000
  python scripts/make_clean_split.py --src data/raw_dataset/detector_yolo

Usage:
  python -m ml.remap_to_coarse                       # from backend/
  python ml/remap_to_coarse.py --copy                # copy images instead of hard-link
"""

from __future__ import annotations

import argparse
import os
import shutil
from collections import Counter

from ml.taxonomy import COARSE_NAMES, FINE_TO_COARSE, NUM_COARSE

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")


def link_or_copy(src: str, dst: str, copy: bool) -> None:
    if os.path.exists(dst):
        return
    if copy:
        shutil.copy2(src, dst)
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def clean_and_remap(lines: list[str]) -> tuple[list[str], Counter, int]:
    """Return (new_lines, per-coarse-class instance counter, dropped_box_count)."""
    out: list[str] = []
    hist: Counter = Counter()
    dropped = 0
    for line in lines:
        parts = line.split()
        if len(parts) < 5:
            if parts:
                dropped += 1
            continue
        try:
            fid = int(float(parts[0]))
            x, y, w, h = (float(v) for v in parts[1:5])
        except ValueError:
            dropped += 1
            continue
        if fid not in FINE_TO_COARSE:
            dropped += 1
            continue
        # clean geometry
        if w <= 0 or h <= 0 or x < 0 or y < 0:
            dropped += 1
            continue
        x = min(1.0, x)
        y = min(1.0, y)
        w = min(1.0, w)
        h = min(1.0, h)
        cid = FINE_TO_COARSE[fid]
        out.append(f"{cid} {x:.6f} {y:.6f} {w:.6f} {h:.6f}\n")
        hist[cid] += 1
    return out, hist, dropped


def process_split(src_root: str, dst_root: str, split: str, copy: bool):
    src_img = os.path.join(src_root, "images", split)
    src_lbl = os.path.join(src_root, "labels", split)
    dst_img = os.path.join(dst_root, "images", split)
    dst_lbl = os.path.join(dst_root, "labels", split)
    os.makedirs(dst_img, exist_ok=True)
    os.makedirs(dst_lbl, exist_ok=True)

    if not os.path.isdir(src_img):
        print(f"  (no {src_img} — skipping split)")
        return Counter(), Counter(), 0, 0, 0

    imgs = [f for f in os.listdir(src_img) if f.lower().endswith(IMG_EXTS)]
    before_hist: Counter = Counter()
    after_hist: Counter = Counter()
    n_dropped = n_empty = n_nolabel = 0

    for i, fn in enumerate(imgs):
        link_or_copy(os.path.join(src_img, fn), os.path.join(dst_img, fn), copy)
        stem = os.path.splitext(fn)[0]
        lbl_in = os.path.join(src_lbl, stem + ".txt")
        lbl_out = os.path.join(dst_lbl, stem + ".txt")
        if not os.path.exists(lbl_in):
            n_nolabel += 1
            continue
        with open(lbl_in, encoding="utf-8", errors="ignore") as fh:
            raw = fh.readlines()
        for ln in raw:
            p = ln.split()
            if len(p) >= 5:
                try:
                    before_hist[int(float(p[0]))] += 1
                except ValueError:
                    pass
        new_lines, hist, dropped = clean_and_remap(raw)
        after_hist.update(hist)
        n_dropped += dropped
        if not new_lines:
            open(lbl_out, "w").close()
            n_empty += 1
        else:
            with open(lbl_out, "w", encoding="utf-8") as fh:
                fh.writelines(new_lines)
        if (i + 1) % 10000 == 0:
            print(f"    {split}: {i + 1:,}/{len(imgs):,}")

    print(
        f"  {split}: {len(imgs):,} images  |  {n_nolabel:,} without a label  |  "
        f"{n_empty:,} empty(neg)  |  {n_dropped:,} boxes dropped in cleaning"
    )
    return before_hist, after_hist, n_dropped, n_empty, n_nolabel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(BACKEND, "data", "unified_yolo"))
    ap.add_argument("--dst", default=os.path.join(BACKEND, "data", "raw_dataset", "detector_yolo"))
    ap.add_argument("--copy", action="store_true", help="copy images instead of hard-linking")
    args = ap.parse_args()

    src_root = os.path.abspath(args.src)
    dst_root = os.path.abspath(args.dst)
    if not os.path.isdir(src_root):
        raise SystemExit(f"--src not found: {src_root}")
    print(f"Remap  {src_root}\n   ->  {dst_root}   ({'copy' if args.copy else 'hard-link'} images)\n")

    total_before: Counter = Counter()
    total_after: Counter = Counter()
    for split in ("train", "valid", "val"):
        if os.path.isdir(os.path.join(src_root, "images", split)):
            b, a, *_ = process_split(src_root, dst_root, split, args.copy)
            total_before.update(b)
            total_after.update(a)

    print("\nPer-class instances  (old fine -> new coarse):")
    print(f"  {'coarse class':24s} {'instances':>12s}")
    for cid in range(NUM_COARSE):
        print(f"  {cid:2d} {COARSE_NAMES[cid]:21s} {total_after.get(cid, 0):>12,}")
    zero = [COARSE_NAMES[c] for c in range(NUM_COARSE) if total_after.get(c, 0) == 0]
    if zero:
        print(f"\n  !! zero-instance coarse classes: {zero}")
        if zero == ["license_plate"]:
            print("     (expected — plates are added next by scripts/add_plates.py)")
    print(f"\nTotal boxes:  before {sum(total_before.values()):,}  ->  after {sum(total_after.values()):,}")
    print(
        '\nNext:  python scripts/add_plates.py --src "<...v13i.yolov8>" '
        "--dst data/raw_dataset/detector_yolo --purge-old --limit 18000"
    )


if __name__ == "__main__":
    main()
