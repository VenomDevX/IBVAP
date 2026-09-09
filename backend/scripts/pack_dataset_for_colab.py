"""
pack_dataset_for_colab.py — make the coarse-detector dataset portable
=====================================================================
The local split (`configs/dataset_coarse.yaml`) hard-codes absolute Windows
paths. This rewrites the split lists to paths *relative to the dataset root*
and emits a Colab-ready yaml, so the same 89k/10k leak-free split works after
you copy the tree to `/content` on Colab.

Run:
  python scripts/pack_dataset_for_colab.py            # write portable files only
  python scripts/pack_dataset_for_colab.py --tar      # also build the upload tar (~33 GB)

Outputs (under backend/data/colab_pack/):
  train_coarse.txt   val_coarse.txt      # ./images/... relative lines
  dataset_coarse.yaml                    # path: .  (root of the extracted tree)
  UPLOAD.md                              # exact tar + Drive-upload commands

With --tar it also writes  data/ibvap_coarse_dataset.tar  containing
  images/  labels/  train_coarse.txt  val_coarse.txt  dataset_coarse.yaml
"""

import argparse
import os
import subprocess
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.path.join(BACKEND, "data", "detector_yolo")   # holds images/ labels/
SPLIT_DIR = os.path.join(BACKEND, "data", "splits")
OUT_DIR = os.path.join(BACKEND, "data", "colab_pack")

NAMES = [
    "person", "car", "bus", "truck", "motorcycle", "bicycle", "license_plate",
    "military_ground_vehicle", "aircraft", "helicopter", "drone_uav",
    "night_vision_object", "animal",
]


def _rel_lines(src_txt: str) -> list[str]:
    root = DATA_ROOT.replace("\\", "/").rstrip("/") + "/"
    out, missing = [], 0
    with open(src_txt, encoding="utf-8") as fh:
        for line in fh:
            p = line.strip().replace("\\", "/")
            if not p:
                continue
            if p.startswith(root):
                p = "./" + p[len(root):]
            elif not p.startswith("./"):
                # already relative or a different layout — keep as-is
                p = "./" + p.lstrip("/")
            if not os.path.isfile(os.path.join(DATA_ROOT, p[2:])):
                missing += 1
            out.append(p)
    if missing:
        print(f"  ! {missing} listed files not found on disk in {os.path.basename(src_txt)}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tar", action="store_true", help="also build the ~33 GB upload tar")
    args = ap.parse_args()

    for d in (DATA_ROOT, SPLIT_DIR):
        if not os.path.isdir(d):
            sys.exit(f"missing {d} — run scripts/make_clean_split.py first")

    os.makedirs(OUT_DIR, exist_ok=True)

    for name in ("train_coarse.txt", "val_coarse.txt"):
        lines = _rel_lines(os.path.join(SPLIT_DIR, name))
        with open(os.path.join(OUT_DIR, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
        print(f"  {name}: {len(lines)} entries")

    yaml_path = os.path.join(OUT_DIR, "dataset_coarse.yaml")
    with open(yaml_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# portable — path is the root of the extracted tar\n")
        fh.write("path: .\n")
        fh.write("train: train_coarse.txt\n")
        fh.write("val: val_coarse.txt\n\n")
        fh.write(f"nc: {len(NAMES)}\n")
        fh.write("names:\n")
        for i, n in enumerate(NAMES):
            fh.write(f"  {i}: {n}\n")
    print(f"  dataset_coarse.yaml -> {yaml_path}")

    tar_path = os.path.join(BACKEND, "data", "ibvap_coarse_dataset.tar")
    with open(os.path.join(OUT_DIR, "UPLOAD.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(
            "# Upload the dataset to Google Drive\n\n"
            "## 1. Build the tar (from backend/)\n\n"
            "```bash\n"
            "tar -C data/detector_yolo -cf data/ibvap_coarse_dataset.tar images labels\n"
            "tar -C data/colab_pack   -rf data/ibvap_coarse_dataset.tar "
            "train_coarse.txt val_coarse.txt dataset_coarse.yaml\n"
            "```\n\n"
            "## 2. Put `data/ibvap_coarse_dataset.tar` in your Drive\n"
            "Drive folder: `MyDrive/ibvap/` (drag-drop, Drive desktop, or rclone).\n"
            "~33 GB — do it once, overnight if your uplink is slow.\n\n"
            "## 3. Open `backend/notebooks/train_colab.ipynb` in Colab and run it.\n"
        )
    print(f"  UPLOAD.md -> {os.path.join(OUT_DIR, 'UPLOAD.md')}")

    if args.tar:
        print(f"\nBuilding {tar_path} (this takes a while)...")
        subprocess.run(["tar", "-C", DATA_ROOT, "-cf", tar_path, "images", "labels"], check=True)
        subprocess.run(["tar", "-C", OUT_DIR, "-rf", tar_path,
                        "train_coarse.txt", "val_coarse.txt", "dataset_coarse.yaml"], check=True)
        gb = os.path.getsize(tar_path) / 1e9
        print(f"done: {tar_path}  ({gb:.1f} GB)")
    else:
        print("\nPortable split files written. Re-run with --tar to build the upload archive,\n"
              "or follow data/colab_pack/UPLOAD.md.")


if __name__ == "__main__":
    main()
