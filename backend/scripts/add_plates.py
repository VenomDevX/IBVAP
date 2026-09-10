"""
add_plates.py — correctly merge a License-Plate dataset into the coarse detector set
==================================================================================
Fixes the merge bug that left every `plate_*` image without a label (class
'license_plate' had zero instances).

What it does:
  1. (optional) removes old label-less `plate_*` images/labels from the target set
  2. reads a Roboflow-style YOLOv8 plate dataset:  <src>/{train,valid,test}/images + labels
     (also tolerates a flat  <src>/images + <src>/labels)
  3. (optional) subsamples to --limit images, keeping whole augmentation groups together
  4. copies images as  plate_<name>.jpg  into <dst>/images/{train,valid}
  5. remaps EVERY source class id -> the coarse 'license_plate' id
  6. writes labels with a robust image->label path resolver (no fragile str.replace)

Usage:
  python scripts/add_plates.py --src "F:/Projects/SIH 26187/License Plate Recognition.v13i.yolov8" \
         --dst data/raw_dataset/detector_yolo --purge-old --limit 18000
  python scripts/make_clean_split.py --src data/raw_dataset/detector_yolo
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/ on path for `ml.*`
import argparse
import glob
import re
import shutil
from collections import defaultdict

try:
    from ml.taxonomy import COARSE_ID

    PLATE_CLASS_ID = COARSE_ID["license_plate"]
except Exception:  # taxonomy import may fail if run oddly; fall back to the known id
    PLATE_CLASS_ID = 6

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
IMG_EXTS = (".jpg", ".jpeg", ".png")
RF_HASH = re.compile(r"\.rf\.[0-9a-fA-F]{6,}\.(?:jpg|jpeg|png|bmp|webp)$", re.I)


def source_key(filename: str) -> str:
    base = RF_HASH.sub("", filename)
    if base == filename:
        base = os.path.splitext(filename)[0]
    return re.sub(r"_jpe?g$", "", base, flags=re.I)


def label_path_for(img_path: str) -> str:
    """Map .../images/.../foo.jpg -> .../labels/.../foo.txt (robust, dir-based)."""
    d, fn = os.path.split(img_path)
    stem = os.path.splitext(fn)[0]
    parts = d.replace("\\", "/").split("/")
    for i in range(len(parts) - 1, -1, -1):
        if parts[i].lower() == "images":
            parts[i] = "labels"
            break
    return "/".join(parts) + "/" + stem + ".txt"


def iter_source_images(src: str):
    """Yield (img_path, out_split) for every image in a Roboflow-ish yolov8 dataset."""
    found = False
    for split in ("train", "valid", "val", "test"):
        img_dir = os.path.join(src, split, "images")
        if os.path.isdir(img_dir):
            found = True
            out_split = "valid" if split in ("valid", "val") else "train"  # test -> train
            for ext in IMG_EXTS:
                for p in glob.glob(os.path.join(img_dir, f"*{ext}")):
                    yield p, out_split
    if not found:
        img_dir = os.path.join(src, "images")
        if os.path.isdir(img_dir):
            for ext in IMG_EXTS:
                for p in glob.glob(os.path.join(img_dir, f"*{ext}")):
                    yield p, "train"
        else:
            raise SystemExit(f"No images under {src} (expected <src>/train/images or <src>/images).")


def subsample(pairs, limit: int):
    """Keep whole source-augmentation groups until ~limit images; deterministic."""
    groups = defaultdict(list)
    for img, split in pairs:
        groups[source_key(os.path.basename(img))].append((img, split))
    out, n = [], 0
    for key in sorted(groups):
        grp = groups[key]
        if n and n + len(grp) > limit:
            break
        out.extend(grp)
        n += len(grp)
    return out


def link_or_copy(src: str, dst: str) -> None:
    """Hard-link when possible (same volume, instant); else copy."""
    if os.path.exists(dst):
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def purge_old_plates(dst_root: str):
    removed = 0
    for split in ("train", "valid"):
        for ext in IMG_EXTS:
            for p in glob.glob(os.path.join(dst_root, "images", split, f"plate_*{ext}")):
                os.remove(p)
                removed += 1
        for p in glob.glob(os.path.join(dst_root, "labels", split, "plate_*.txt")):
            os.remove(p)
    for c in glob.glob(os.path.join(dst_root, "**", "*.cache"), recursive=True):
        os.remove(c)
    print(f"Purged {removed:,} old plate images (+ any *.cache) from {dst_root}.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="Roboflow-style YOLOv8 plate dataset root")
    ap.add_argument(
        "--dst",
        default=os.path.join(BACKEND, "data", "raw_dataset", "detector_yolo"),
        help="target dataset root (default: backend/data/raw_dataset/detector_yolo)",
    )
    ap.add_argument("--limit", type=int, default=0, help="cap images added (whole aug-groups kept together); 0 = all")
    ap.add_argument("--purge-old", action="store_true")
    ap.add_argument("--prefix", default="plate")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = os.path.abspath(args.src)
    dst_root = os.path.abspath(args.dst)
    if not os.path.isdir(src):
        raise SystemExit(f"--src not found: {src}")
    print(f"plate merge  {src}\n         ->  {dst_root}   (class id {PLATE_CLASS_ID})")

    if args.purge_old and not args.dry_run:
        purge_old_plates(dst_root)

    pairs = list(iter_source_images(src))
    total_available = len(pairs)
    if args.limit and total_available > args.limit:
        pairs = subsample(pairs, args.limit)
    print(f"images: {total_available:,} available -> {len(pairs):,} selected")

    copied_img = copied_box = no_label = empty_label = 0
    for img_path, out_split in pairs:
        fn = os.path.basename(img_path)
        out_img = os.path.join(dst_root, "images", out_split, f"{args.prefix}_{fn}")
        out_lbl = os.path.join(dst_root, "labels", out_split, f"{args.prefix}_{os.path.splitext(fn)[0]}.txt")
        lbl_src = label_path_for(img_path)
        if args.dry_run:
            no_label += not os.path.exists(lbl_src)
            copied_img += os.path.exists(lbl_src)
            continue

        os.makedirs(os.path.dirname(out_img), exist_ok=True)
        os.makedirs(os.path.dirname(out_lbl), exist_ok=True)
        link_or_copy(img_path, out_img)
        copied_img += 1

        if not os.path.exists(lbl_src):
            no_label += 1
            open(out_lbl, "w").close()
            continue
        n_box = 0
        with open(lbl_src, encoding="utf-8", errors="ignore") as fin, open(out_lbl, "w", encoding="utf-8") as fout:
            for line in fin:
                p = line.split()
                if len(p) < 5:
                    continue
                p[0] = str(PLATE_CLASS_ID)
                fout.write(" ".join(p[:5]) + "\n")
                n_box += 1
        copied_box += n_box
        empty_label += n_box == 0

    print(f"\n{'DRY RUN — ' if args.dry_run else ''}summary:")
    print(f"  images written        : {copied_img:,}")
    print(f"  license_plate boxes    : {copied_box:,}")
    print(f"  images w/o source label: {no_label:,}")
    print(f"  images w/ empty label  : {empty_label:,}")
    if not args.dry_run:
        print("\nNext:  python scripts/make_clean_split.py --src data/raw_dataset/detector_yolo")


if __name__ == "__main__":
    main()
