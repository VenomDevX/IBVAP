"""cleanup_data.py — report and optionally reclaim source data space.

Run ONLY after training has succeeded. Defaults to a dry-run report; deletion
requires an explicit flag AND a typed confirmation.

Verdicts:
  safe    reconstructible or empty; deleting costs nothing
  verify  likely redundant, but confirm the overlap first
  keep    sole copy of source imagery; deleting prevents rebuilding

The 'keep' verdicts are the important ones. data/dataset/ holds only the
curated subset — roughly 50k of 119,706 detector images and a capped selection
of the crops. Delete the sources and you can never re-run build_dataset.py at a
different threshold, cap or target, which is exactly what you will want to do
after seeing the first training results.

Usage:
  python scripts/cleanup_data.py                 # report only
  python scripts/cleanup_data.py --delete safe   # ~34 GB, tar + empty dirs
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

TARGETS: list[tuple[str, str, str]] = [
    ("ibvap_coarse_dataset.tar", "safe",
     "Colab packing artifact. Colab is no longer used and it is rebuildable "
     "from detector_yolo via scripts/pack_dataset_for_colab.py."),
    ("colab_pack", "safe", "Empty."),
    ("custom", "safe", "Empty."),
    ("plates", "safe", "Empty."),
    ("unified_yolo", "safe",
     "Superseded by detector_yolo. Verified 2026-09-10: of its 101,434 images, "
     "81,606 are already in detector_yolo and the other 19,828 are plate_* "
     "images with NO label file (0 of 400 sampled had one) - the label-less "
     "plate merge bug. Nothing trainable is unique to it."),
    ("cropped_classes", "keep",
     "Sole copy of the ~500k crops not selected. Needed to re-tune the prune "
     "threshold or per-class cap."),
    ("detector_yolo", "keep",
     "Sole copy of the source imagery. data/dataset/ holds only the curated "
     "~50k subset."),
]


def size_of(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    total = 0
    for f in p.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except OSError:
                pass
    return total


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


def main() -> None:
    ap = argparse.ArgumentParser(description="Report/reclaim source data space")
    ap.add_argument("--delete", choices=["safe", "verify"],
                    help="actually delete entries carrying this verdict")
    args = ap.parse_args()

    manifest = DATA / "dataset" / "manifest.json"
    if not manifest.exists():
        raise SystemExit(
            "refusing: data/dataset/manifest.json not found — nothing has been built"
        )
    if "emit" not in json.loads(manifest.read_text(encoding="utf-8")):
        raise SystemExit(
            "refusing: the manifest shows no completed emit stage. Finish "
            "scripts/build_dataset.py, and ideally train on it, before deleting sources."
        )

    print(f"{'target':<30}{'size':>10}  {'verdict':<8} reason")
    print("-" * 110)
    reclaim = 0
    matched = []
    for name, verdict, reason in TARGETS:
        p = DATA / name
        if not p.exists():
            continue
        s = size_of(p)
        print(f"{name:<30}{human(s):>10}  {verdict:<8} {reason}")
        if args.delete and verdict == args.delete:
            reclaim += s
            matched.append((name, p))

    if not args.delete:
        print("\nDry run — nothing deleted.")
        print("  python scripts/cleanup_data.py --delete safe    # reclaim the safe entries")
        return

    if not matched:
        print(f"\nNothing carries the '{args.delete}' verdict.")
        return

    print(f"\nAbout to PERMANENTLY delete {len(matched)} entr(y/ies), "
          f"reclaiming ~{human(reclaim)}:")
    for name, _ in matched:
        print(f"  - data/{name}")
    if input("\nType DELETE to confirm: ").strip() != "DELETE":
        raise SystemExit("aborted — nothing was deleted")

    for name, p in matched:
        print(f"  removing data/{name} ...")
        if p.is_file():
            p.unlink()
        else:
            shutil.rmtree(p, ignore_errors=True)
    print(f"Reclaimed ~{human(reclaim)}.")


if __name__ == "__main__":
    main()
