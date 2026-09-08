"""
verify_dataset.py — sanity gate to run before every detector training
====================================================================
Checks a YOLO data.yaml (with .txt file lists or split dirs):
  * per-class instance histogram          -> every class non-zero, none absurdly dominant
  * image / label parity                  -> counts, missing labels, empty (negative) files
  * train/val leakage                     -> 0 shared group keys (source image + MOT/VIRAT clip)
  * bbox size distribution                -> flags very small boxes (lost at the training imgsz)
  * 20 random label files pretty-printed  -> eyeball check

Usage:
  python -m ml.verify_dataset --data configs/dataset_coarse.yaml
  python -m ml.verify_dataset --data configs/dataset_coarse.yaml --imgsz 640
"""

from __future__ import annotations

import argparse
import os
import random
import re
from collections import Counter

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")

try:
    from ml.make_clean_split import group_key  # type: ignore
except Exception:
    import sys
    sys.path.insert(0, os.path.join(BACKEND, "scripts"))
    from make_clean_split import group_key  # type: ignore


def resolve_images(spec: str, base: str) -> list[str]:
    """A data.yaml train/val entry -> list of absolute image paths."""
    p = spec if os.path.isabs(spec) else os.path.join(base, spec)
    p = os.path.normpath(p)
    if os.path.isfile(p) and p.lower().endswith(".txt"):
        with open(p, "r", encoding="utf-8") as fh:
            return [ln.strip().replace("\\", "/") for ln in fh if ln.strip()]
    if os.path.isdir(p):
        return [os.path.join(p, f).replace("\\", "/")
                for f in os.listdir(p) if f.lower().endswith(IMG_EXTS)]
    raise SystemExit(f"cannot resolve images from: {spec} -> {p}")


def label_for(img: str) -> str:
    lbl = re.sub(r"\.(?:jpg|jpeg|png|bmp|webp)$", ".txt", img, flags=re.I)
    return lbl.replace("/images/", "/labels/")


def scan(images: list[str]):
    hist = Counter()
    small = 0
    total_box = 0
    n_missing = n_empty = n_ok = 0
    for img in images:
        lbl = label_for(img)
        if not os.path.exists(lbl):
            n_missing += 1
            continue
        with open(lbl, "r", encoding="utf-8", errors="ignore") as fh:
            lines = [ln for ln in fh if ln.strip()]
        if not lines:
            n_empty += 1
            continue
        n_ok += 1
        for ln in lines:
            p = ln.split()
            if len(p) < 5:
                continue
            try:
                cid = int(float(p[0])); w = float(p[3]); h = float(p[4])
            except ValueError:
                continue
            hist[cid] += 1
            total_box += 1
            if w * h < (16 / 640) ** 2:  # < ~16px box at 640
                small += 1
    return hist, n_ok, n_empty, n_missing, total_box, small


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="path to a YOLO data.yaml")
    ap.add_argument("--imgsz", type=int, default=640)
    args = ap.parse_args()

    data_path = os.path.abspath(args.data)
    with open(data_path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    base = cfg.get("path", os.path.dirname(data_path))
    names = [cfg["names"][i] for i in range(cfg["nc"])] if isinstance(cfg["names"], dict) else cfg["names"]

    train_imgs = resolve_images(cfg["train"], base)
    val_imgs = resolve_images(cfg["val"], base)
    print(f"data.yaml : {data_path}")
    print(f"classes   : {len(names)}")
    print(f"train     : {len(train_imgs):,} images")
    print(f"val       : {len(val_imgs):,} images\n")

    problems = []

    # --- leakage ---
    tr_keys = {group_key(os.path.basename(p)) for p in train_imgs}
    va_keys = {group_key(os.path.basename(p)) for p in val_imgs}
    overlap = tr_keys & va_keys
    print(f"[leak]  train groups {len(tr_keys):,}  val groups {len(va_keys):,}  "
          f"overlap {len(overlap)}")
    if overlap:
        problems.append(f"{len(overlap)} groups in both train and val")
        for k in list(overlap)[:5]:
            print(f"        e.g. {k}")

    # --- per split scan ---
    for label, imgs in (("train", train_imgs), ("val", val_imgs)):
        hist, n_ok, n_empty, n_missing, total_box, small = scan(imgs)
        print(f"\n[{label}]  labelled {n_ok:,} | empty(neg) {n_empty:,} | "
              f"missing-label {n_missing:,} | boxes {total_box:,} | tiny(<16px@640) {small:,}")
        print(f"  {'class':24s} {'instances':>12s}")
        for cid in range(len(names)):
            n = hist.get(cid, 0)
            flag = "  <== ZERO" if n == 0 else ("  <== dominant" if n > 0.6 * total_box else "")
            print(f"  {cid:2d} {str(names[cid]):21s} {n:>12,}{flag}")
        if n_missing and label == "val":
            problems.append(f"val has {n_missing} images with no label file")
        zeros = [names[c] for c in range(len(names)) if hist.get(c, 0) == 0]
        if zeros:
            problems.append(f"{label}: zero-instance classes {zeros}")

    # --- sample labels ---
    print("\n[sample] 20 random val labels:")
    for img in random.sample(val_imgs, min(20, len(val_imgs))):
        lbl = label_for(img)
        if not os.path.exists(lbl):
            print(f"  {os.path.basename(img)}  -> MISSING LABEL")
            continue
        with open(lbl, "r", encoding="utf-8") as fh:
            body = fh.read().strip().replace("\n", " | ")
        print(f"  {os.path.basename(img)[:60]:60s} -> {body[:90] or '(empty/neg)'}")

    print("\n" + "=" * 64)
    if problems:
        print("PROBLEMS:")
        for p in problems:
            print(f"  - {p}")
        raise SystemExit(1)
    print("OK — dataset looks trainable.")


if __name__ == "__main__":
    main()
