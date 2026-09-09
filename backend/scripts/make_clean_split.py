"""
make_clean_split.py — leak-free, clip-aware train/val split
==========================================================
The raw merged data leaks: Roboflow augments each source image several times
(`<id>_jpg.rf.<hash>.jpg`) and scatters the copies across train and val, and
MOT/VIRAT contribute many near-identical consecutive video frames. Either way a
random split puts near-twins on both sides and inflates val mAP.

This script does NOT move or copy any image. It re-partitions the *existing*
files into a new train/val assignment by a GROUP KEY, so near-twins never split:

  * Roboflow augmentations  -> grouped by source image (strip `.rf.<hash>`)
  * MOT / VIRAT frames      -> grouped by source clip  (strip trailing `_<frame>`)

Split is deterministic (seeded), stratified per source family, ~10% val.
Images with NO label file (e.g. the old label-less plate_* merge bug) are dropped;
empty `.txt` files are kept as background negatives.

Output (default --tag coarse):
  backend/data/splits/train_coarse.txt
  backend/data/splits/val_coarse.txt
  backend/configs/dataset_coarse.yaml

Usage:
  python scripts/make_clean_split.py --src data/detector_yolo
  python scripts/make_clean_split.py --src data/detector_yolo --val-fraction 0.15
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/ on path for `ml.*`
import argparse
import hashlib
import re
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
SPLIT_DIR = os.path.join(BACKEND, "data", "splits")
CONFIG_DIR = os.path.join(BACKEND, "configs")

IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
RF_HASH = re.compile(r"\.rf\.[0-9a-fA-F]{6,}\.(?:jpg|jpeg|png|bmp|webp)$", re.I)
# our own frame-sequence prefixes (from convert_mot17 / convert_virat)
CLIP_PREFIXES = ("mot_", "virat_")
TRAILING_FRAME = re.compile(r"_\d{3,}$")


def source_key(filename: str) -> str:
    base = RF_HASH.sub("", filename)
    if base == filename:  # not a Roboflow-augmented name
        base = os.path.splitext(filename)[0]  # ...so just drop the extension
    return re.sub(r"_jpe?g$", "", base, flags=re.I)


def group_key(filename: str) -> str:
    """Twin-safe grouping key: source image, or source clip for MOT/VIRAT frames."""
    k = source_key(filename)
    if k.startswith(CLIP_PREFIXES):
        k = TRAILING_FRAME.sub("", k)  # drop the frame number -> clip id
    return k


def family(filename: str) -> str:
    m = re.match(r"([a-zA-Z]+)", filename)
    return m.group(1) if m else "misc"


def stable_bucket(key: str, seed: int) -> float:
    h = hashlib.md5(f"{seed}:{key}".encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def label_for(abs_img: str) -> str:
    lbl = re.sub(r"\.(?:jpg|jpeg|png|bmp|webp)$", ".txt", abs_img, flags=re.I)
    return lbl.replace("/images/", "/labels/")


def coarse_names():
    try:
        from ml.taxonomy import COARSE_NAMES

        return list(COARSE_NAMES)
    except Exception:
        return None


def fine_names():
    import yaml

    with open(os.path.join(CONFIG_DIR, "dataset.yaml"), encoding="utf-8") as fh:
        src = yaml.safe_load(fh)
    return [src["names"][i] for i in range(src["nc"])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--src",
        default=os.path.join(BACKEND, "data", "detector_yolo"),
        help="dataset root containing images/ and labels/",
    )
    ap.add_argument("--tag", default="coarse", help="suffix for the output files")
    ap.add_argument("--names", choices=["coarse", "fine"], default="coarse")
    ap.add_argument("--val-fraction", type=float, default=0.10)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--keep-unlabeled", action="store_true")
    args = ap.parse_args()

    root = os.path.abspath(args.src)
    img_root = os.path.join(root, "images")
    if not os.path.isdir(img_root):
        raise SystemExit(f"no images/ under {root}")

    # 1. collect images, drop only those with NO label file
    all_files = []
    dropped_missing = Counter()
    kept_negatives = Counter()
    for sub in ("train", "valid", "val"):
        d = os.path.join(img_root, sub)
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if not f.lower().endswith(IMG_EXTS):
                continue
            abs_img = os.path.join(d, f).replace("\\", "/")
            lbl = label_for(abs_img)
            if os.path.exists(lbl):
                if os.path.getsize(lbl) == 0:
                    kept_negatives[family(f)] += 1
                all_files.append((abs_img, f))
            elif args.keep_unlabeled:
                all_files.append((abs_img, f))
            else:
                dropped_missing[family(f)] += 1

    if not all_files:
        raise SystemExit(f"no usable images under {img_root}")

    if kept_negatives:
        print(f"Kept {sum(kept_negatives.values()):,} background negatives (empty .txt).")
    if sum(dropped_missing.values()):
        print(f"Dropped {sum(dropped_missing.values()):,} images with no label file:")
        for fam, n in dropped_missing.most_common():
            print(f"    {fam:12s} {n:>7,}")

    # 2. group by twin-safe key
    by_key = defaultdict(list)
    key_family = {}
    for abs_path, fname in all_files:
        k = group_key(fname)
        by_key[k].append(abs_path)
        key_family.setdefault(k, family(fname))
    print(f"{len(all_files):,} images  ->  {len(by_key):,} twin-safe groups")

    # 3. stratified deterministic assignment per family
    fam_keys = defaultdict(list)
    for k, fam in key_family.items():
        fam_keys[fam].append(k)
    val_keys = set()
    for fam, keys in fam_keys.items():
        picked = {k for k in keys if stable_bucket(k, args.seed) < args.val_fraction}
        # families with few groups (e.g. a handful of MOT/VIRAT clips) can hash to none
        if not picked and len(keys) >= 2:
            picked = {sorted(keys, key=lambda k: stable_bucket(k, args.seed))[0]}
        val_keys |= picked

    # 4. materialise lists
    train_paths, val_paths = [], []
    for k, paths in by_key.items():
        (val_paths if k in val_keys else train_paths).extend(paths)
    train_paths.sort()
    val_paths.sort()

    # 5. sanity: no group on both sides
    tr_keys = {group_key(os.path.basename(p)) for p in train_paths}
    assert not (tr_keys & val_keys), "LEAK: a group landed on both sides"

    # 6. write lists
    os.makedirs(SPLIT_DIR, exist_ok=True)
    train_txt = os.path.join(SPLIT_DIR, f"train_{args.tag}.txt")
    val_txt = os.path.join(SPLIT_DIR, f"val_{args.tag}.txt")
    with open(train_txt, "w", encoding="utf-8") as fh:
        fh.write("\n".join(train_paths) + "\n")
    with open(val_txt, "w", encoding="utf-8") as fh:
        fh.write("\n".join(val_paths) + "\n")

    # 7. write dataset yaml
    names = coarse_names() if args.names == "coarse" else fine_names()
    if names is None:
        raise SystemExit("could not resolve class names (ml.taxonomy import failed)")
    out_yaml = os.path.join(CONFIG_DIR, f"dataset_{args.tag}.yaml")
    with open(out_yaml, "w", encoding="utf-8") as fh:
        fh.write("# Leak-free, clip-aware split — scripts/make_clean_split.py\n")
        fh.write(f"# grouped by source image + MOT/VIRAT clip; val_fraction={args.val_fraction} seed={args.seed}\n\n")
        fh.write(f"path: {root.replace(chr(92), '/')}\n")
        fh.write(f"train: {train_txt.replace(chr(92), '/')}\n")
        fh.write(f"val: {val_txt.replace(chr(92), '/')}\n\n")
        fh.write(f"nc: {len(names)}\n")
        fh.write("names:\n")
        for i, n in enumerate(names):
            fh.write(f"  {i}: {n}\n")

    # 8. report
    tf = Counter(family(os.path.basename(p)) for p in train_paths)
    vf = Counter(family(os.path.basename(p)) for p in val_paths)
    print(
        f"\nSplit:  train {len(train_paths):,}  |  val {len(val_paths):,} "
        f"({100 * len(val_paths) / len(all_files):.1f}% val)"
    )
    print("Per-family (train / val):")
    for fam in sorted(set(tf) | set(vf), key=lambda k: -(tf[k] + vf[k])):
        n_t, n_v = tf.get(fam, 0), vf.get(fam, 0)
        print(f"  {fam:12s} {n_t:>8,} / {n_v:>6,}   ({100 * n_v / max(1, n_t + n_v):4.1f}% val)")
    print(f"\nWrote:\n  {train_txt}\n  {val_txt}\n  {out_yaml}")
    print(f"\nNext: python scripts/train_yolo.py --data configs/dataset_{args.tag}.yaml --model yolo11s.pt")


if __name__ == "__main__":
    main()
