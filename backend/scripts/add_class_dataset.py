"""
add_class_dataset.py — merge an external YOLO dataset into the coarse detector set
================================================================================
Generalises scripts/add_plates.py to any coarse class. Use it to top up the
starved aerial / military classes (drone_uav, helicopter, aircraft,
military_ground_vehicle) with dedicated datasets (VisDrone, xView, a Roboflow
"military aircraft" set, ...).

What it does:
  1. reads a Roboflow-style YOLOv8 dataset:  <src>/{train,valid,test}/images + labels
     (also tolerates a flat  <src>/images + <src>/labels)
  2. (optional) keeps only boxes whose SOURCE class id is in --src-classes
  3. (optional) subsamples to --limit images (whole aug-groups kept together)
  4. hard-links images as  <prefix>_<name>.jpg  into <dst>/images/{train,valid}
  5. rewrites EVERY kept box to the target coarse class id
  6. keeps empty label files as background negatives

Usage (from backend/):
  # a single-class drone dataset -> everything becomes drone_uav
  python scripts/add_class_dataset.py --src "F:/datasets/drone.v2i.yolov8" --class drone_uav --limit 6000

  # VisDrone-style multi-class set: keep only its 'car'(id 3) + 'van'(id 4) as ... nothing here;
  # for aircraft keep only the source ids that are planes:
  python scripts/add_class_dataset.py --src "F:/datasets/military-aircraft" --class aircraft \
         --src-classes 0,1,2,5 --limit 8000

Then:
  python scripts/make_clean_split.py --src data/detector_yolo
  python scripts/pack_dataset_for_colab.py --tar
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/ on path
import argparse
import glob
import re
import shutil
from collections import defaultdict

from ml.taxonomy import COARSE_ID

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
    d, fn = os.path.split(img_path)
    stem = os.path.splitext(fn)[0]
    parts = d.replace("\\", "/").split("/")
    for i in range(len(parts) - 1, -1, -1):
        if parts[i].lower() == "images":
            parts[i] = "labels"
            break
    return "/".join(parts) + "/" + stem + ".txt"


def iter_source_images(src: str):
    found = False
    for split in ("train", "valid", "val", "test"):
        img_dir = os.path.join(src, split, "images")
        if os.path.isdir(img_dir):
            found = True
            out_split = "valid" if split in ("valid", "val") else "train"
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
    if os.path.exists(dst):
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def purge_old(dst_root: str, prefix: str):
    removed = 0
    for split in ("train", "valid"):
        for ext in IMG_EXTS:
            for p in glob.glob(os.path.join(dst_root, "images", split, f"{prefix}_*{ext}")):
                os.remove(p); removed += 1
        for p in glob.glob(os.path.join(dst_root, "labels", split, f"{prefix}_*.txt")):
            os.remove(p)
    for c in glob.glob(os.path.join(dst_root, "**", "*.cache"), recursive=True):
        os.remove(c)
    print(f"Purged {removed:,} old {prefix}_* images (+ any *.cache).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="Roboflow-style YOLOv8 dataset root")
    ap.add_argument("--class", dest="cls", required=True,
                    help=f"target coarse class — one of: {', '.join(COARSE_ID)}")
    ap.add_argument("--dst", default=os.path.join(BACKEND, "data", "detector_yolo"))
    ap.add_argument("--src-classes", default="",
                    help="comma list of SOURCE class ids to keep (default: keep all)")
    ap.add_argument("--limit", type=int, default=0, help="cap images added; 0 = all")
    ap.add_argument("--prefix", default="", help="filename prefix (default: the class name)")
    ap.add_argument("--purge-old", action="store_true", help="remove a previous merge with this prefix")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.cls not in COARSE_ID:
        raise SystemExit(f"--class must be one of: {', '.join(COARSE_ID)}")
    target_id = COARSE_ID[args.cls]
    prefix = args.prefix or args.cls
    keep = {int(x) for x in args.src_classes.split(",") if x.strip() != ""} if args.src_classes else None

    src = os.path.abspath(args.src)
    dst_root = os.path.abspath(args.dst)
    if not os.path.isdir(src):
        raise SystemExit(f"--src not found: {src}")
    print(f"merge  {src}\n    ->  {dst_root}   (class '{args.cls}' = id {target_id}, prefix '{prefix}')")
    if keep is not None:
        print(f"    keeping only source class ids: {sorted(keep)}")

    if args.purge_old and not args.dry_run:
        purge_old(dst_root, prefix)

    pairs = list(iter_source_images(src))
    total = len(pairs)
    if args.limit and total > args.limit:
        pairs = subsample(pairs, args.limit)
    print(f"images: {total:,} available -> {len(pairs):,} selected")

    n_img = n_box = n_nolabel = n_empty = 0
    for img_path, out_split in pairs:
        fn = os.path.basename(img_path)
        out_img = os.path.join(dst_root, "images", out_split, f"{prefix}_{fn}")
        out_lbl = os.path.join(dst_root, "labels", out_split, f"{prefix}_{os.path.splitext(fn)[0]}.txt")
        lbl_src = label_path_for(img_path)
        if args.dry_run:
            n_nolabel += not os.path.exists(lbl_src)
            n_img += os.path.exists(lbl_src)
            continue

        os.makedirs(os.path.dirname(out_img), exist_ok=True)
        os.makedirs(os.path.dirname(out_lbl), exist_ok=True)
        link_or_copy(img_path, out_img)
        n_img += 1

        if not os.path.exists(lbl_src):
            n_nolabel += 1
            open(out_lbl, "w").close()
            continue

        kept = 0
        with open(lbl_src, "r", encoding="utf-8", errors="ignore") as fin, \
             open(out_lbl, "w", encoding="utf-8") as fout:
            for line in fin:
                p = line.split()
                if len(p) < 5:
                    continue
                try:
                    sid = int(float(p[0]))
                except ValueError:
                    continue
                if keep is not None and sid not in keep:
                    continue
                fout.write(f"{target_id} " + " ".join(p[1:5]) + "\n")
                kept += 1
        n_box += kept
        n_empty += (kept == 0)

    print(f"\n{'DRY RUN — ' if args.dry_run else ''}summary:")
    print(f"  images written        : {n_img:,}")
    print(f"  {args.cls} boxes        : {n_box:,}")
    print(f"  images w/o source label: {n_nolabel:,}")
    print(f"  images w/ empty label  : {n_empty:,}")
    if not args.dry_run:
        print("\nNext:\n  python scripts/make_clean_split.py --src data/detector_yolo"
              "\n  python scripts/pack_dataset_for_colab.py --tar")


if __name__ == "__main__":
    main()
