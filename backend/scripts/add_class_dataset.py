"""
add_class_dataset.py — merge an external YOLO dataset into the coarse detector set
================================================================================
Generalises scripts/add_plates.py. Use it to top up the starved aerial / military
classes (drone_uav, helicopter, aircraft, military_ground_vehicle) from dedicated
datasets.

Class mapping — pick ONE:
  --class NAME            every kept box  -> that coarse class
  --map "0:aircraft,3:military_ground_vehicle,..."   per-source-id -> coarse class
  --taxonomy             read <src>/data.yaml `names:` and map each name through
                        ml.taxonomy (FINE_NAMES -> FINE_TO_COARSE). Unmapped names
                        are skipped. Perfect for the 73-class "Border Defence" set.

Also:
  --src-classes 0,2      keep only these SOURCE ids (before mapping); with --class
  --limit N              cap images added (whole aug-groups kept together)
  --prefix TAG           filename prefix (default: --class name, else 'ext')
  polygon labels (class + N*x,y) are collapsed to their bounding box automatically

Usage (from backend/):
  python scripts/add_class_dataset.py --src "J:/Data set/Border Defence.v1i.yolov8" --taxonomy --prefix borderdef --limit 12000
  python scripts/add_class_dataset.py --src "J:/Data set/Militry field object detection.yolov8 (1)" --map "0:aircraft,2:aircraft,3:military_ground_vehicle" --prefix milfield
  python scripts/add_class_dataset.py --src "J:/Data set/drone detection.v2i.yolov8" --class drone_uav --src-classes 0 --prefix drone --limit 5000

Then:
  python scripts/make_clean_split.py --src data/detector_yolo
  python scripts/pack_dataset_for_colab.py --tar
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import argparse
import glob
import re
import shutil
from collections import defaultdict

from ml.taxonomy import COARSE_ID, FINE_NAMES, FINE_TO_COARSE

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
IMG_EXTS = (".jpg", ".jpeg", ".png")
RF_HASH = re.compile(r"\.rf\.[0-9a-fA-F]{6,}\.(?:jpg|jpeg|png|bmp|webp)$", re.I)

# name (lowercased) -> coarse id, from the old fine taxonomy
_FINE_NAME_TO_COARSE = {FINE_NAMES[fid].lower(): FINE_TO_COARSE[fid] for fid in FINE_NAMES}


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


def to_box(parts: list[str]):
    """(sid, x, y, w, h) from a YOLO box (5 tok) OR a polygon (class + N*x,y). None if unparseable."""
    try:
        sid = int(float(parts[0]))
        vals = [float(v) for v in parts[1:]]
    except ValueError:
        return None
    if len(vals) == 4:
        x, y, w, h = vals
    elif len(vals) >= 6 and len(vals) % 2 == 0:
        xs = vals[0::2]
        ys = vals[1::2]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        x, y, w, h = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
    else:
        return None
    x = min(1.0, max(0.0, x))
    y = min(1.0, max(0.0, y))
    w = min(1.0, max(0.0, w))
    h = min(1.0, max(0.0, h))
    if w <= 0 or h <= 0:
        return None
    return sid, x, y, w, h


def load_src_names(src: str) -> dict[int, str]:
    for cand in ("data.yaml", "data.yml"):
        p = os.path.join(src, cand)
        if os.path.isfile(p):
            import yaml

            names = yaml.safe_load(open(p, encoding="utf-8")).get("names")
            if isinstance(names, dict):
                return {int(k): str(v) for k, v in names.items()}
            if isinstance(names, list):
                return {i: str(v) for i, v in enumerate(names)}
    raise SystemExit(f"--taxonomy needs {src}/data.yaml with a names: block")


def purge_old(dst_root: str, prefix: str):
    removed = 0
    for split in ("train", "valid"):
        for ext in IMG_EXTS:
            for p in glob.glob(os.path.join(dst_root, "images", split, f"{prefix}_*{ext}")):
                os.remove(p)
                removed += 1
        for p in glob.glob(os.path.join(dst_root, "labels", split, f"{prefix}_*.txt")):
            os.remove(p)
    for c in glob.glob(os.path.join(dst_root, "**", "*.cache"), recursive=True):
        os.remove(c)
    print(f"Purged {removed:,} old {prefix}_* images (+ any *.cache).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--class", dest="cls", default="", help=f"one of: {', '.join(COARSE_ID)}")
    ap.add_argument("--map", default="", help='"srcid:coarse,srcid:coarse,..."')
    ap.add_argument("--taxonomy", action="store_true", help="map via <src>/data.yaml names -> ml.taxonomy")
    ap.add_argument("--dst", default=os.path.join(BACKEND, "data", "detector_yolo"))
    ap.add_argument("--src-classes", default="", help="keep only these source ids (with --class)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--prefix", default="")
    ap.add_argument("--purge-old", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = os.path.abspath(args.src)
    dst_root = os.path.abspath(args.dst)
    if not os.path.isdir(src):
        raise SystemExit(f"--src not found: {src}")

    modes = sum(bool(x) for x in (args.cls, args.map, args.taxonomy))
    if modes != 1:
        raise SystemExit("pick exactly one of --class / --map / --taxonomy")

    # build  src_id -> target coarse id
    id_map: dict[int, int] = {}
    single_id = None
    keep = {int(x) for x in args.src_classes.split(",") if x.strip()} if args.src_classes else None
    if args.cls:
        if args.cls not in COARSE_ID:
            raise SystemExit(f"--class must be one of: {', '.join(COARSE_ID)}")
        single_id = COARSE_ID[args.cls]
        default_prefix = args.cls
    elif args.map:
        for pair in args.map.split(","):
            sid, cname = pair.split(":")
            cname = cname.strip()
            if cname not in COARSE_ID:
                raise SystemExit(f"unknown coarse class in --map: {cname}")
            id_map[int(sid)] = COARSE_ID[cname]
        default_prefix = "ext"
    else:  # taxonomy
        src_names = load_src_names(src)
        unmapped = []
        for sid, nm in src_names.items():
            key = nm.strip().lower()
            if key in _FINE_NAME_TO_COARSE:
                id_map[sid] = _FINE_NAME_TO_COARSE[key]
            else:
                unmapped.append(nm)
        if unmapped:
            print(f"  taxonomy: {len(unmapped)} source names not in taxonomy, skipped: {unmapped[:10]}")
        default_prefix = "ext"

    prefix = args.prefix or default_prefix
    print(f"merge  {src}\n    ->  {dst_root}   (prefix '{prefix}')")
    if id_map:
        from collections import Counter

        tgt = Counter(id_map.values())
        from ml.taxonomy import COARSE_NAMES

        print("    mapping -> " + ", ".join(f"{COARSE_NAMES[c]}:{n}src" for c, n in tgt.items()))

    if args.purge_old and not args.dry_run:
        purge_old(dst_root, prefix)

    pairs = list(iter_source_images(src))
    total = len(pairs)
    if args.limit and total > args.limit:
        pairs = subsample(pairs, args.limit)
    print(f"images: {total:,} available -> {len(pairs):,} selected")

    n_img = n_box = n_nolabel = n_empty = 0
    per_class: dict[int, int] = defaultdict(int)
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
        with open(lbl_src, encoding="utf-8", errors="ignore") as fin, open(out_lbl, "w", encoding="utf-8") as fout:
            for line in fin:
                p = line.split()
                if len(p) < 5:
                    continue
                box = to_box(p)
                if box is None:
                    continue
                sid, x, y, w, h = box
                if single_id is not None:
                    if keep is not None and sid not in keep:
                        continue
                    tid = single_id
                else:
                    if sid not in id_map:
                        continue
                    tid = id_map[sid]
                fout.write(f"{tid} {x:.6f} {y:.6f} {w:.6f} {h:.6f}\n")
                per_class[tid] += 1
                kept += 1
        n_box += kept
        n_empty += kept == 0

    from ml.taxonomy import COARSE_NAMES

    print(f"\n{'DRY RUN — ' if args.dry_run else ''}summary:")
    print(f"  images written        : {n_img:,}")
    print(f"  boxes written          : {n_box:,}")
    for cid, cnt in sorted(per_class.items()):
        print(f"    {COARSE_NAMES[cid]:24s} {cnt:,}")
    print(f"  images w/o source label: {n_nolabel:,}")
    print(f"  images w/ empty label  : {n_empty:,}")
    if not args.dry_run:
        print(
            "\nNext:\n  python scripts/make_clean_split.py --src data/detector_yolo"
            "\n  python scripts/pack_dataset_for_colab.py --tar"
        )


if __name__ == "__main__":
    main()
