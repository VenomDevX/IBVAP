"""Stage 6 — write the release dataset and verify its integrity.

Copies are resumable: a destination file that already exists at the same size is
skipped, so re-running after an interruption (or a full disk) continues rather
than starting over. This is the slowest stage — ~75k files — so resumability is
not a nicety.

The verify() pass is a hard gate, not advice. It fails the build on a missing
label, an out-of-range class id, or a filename present in both splits.
"""

from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path

from ml.dataset_build.index import ImageRecord, label_path_for
from ml.taxonomy import COARSE_NAMES, NUM_COARSE


def _copy(src: Path, dst: Path) -> bool:
    """Copy unless an identical-size file is already there. True if copied."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        if dst.exists() and dst.stat().st_size == src.stat().st_size:
            return False
    except OSError:
        pass
    shutil.copy2(src, dst)
    return True


def emit_detector(
    train: list[ImageRecord], val: list[ImageRecord], out_root: Path,
    progress: int = 0,
) -> dict:
    out_root = Path(out_root)
    stats = {"train": 0, "val": 0, "copied": 0, "skipped": 0, "no_label": 0}
    n = 0
    for split, recs in (("train", train), ("val", val)):
        for r in recs:
            src = Path(r.path)
            name = src.name
            if _copy(src, out_root / "detector" / "images" / split / name):
                stats["copied"] += 1
            else:
                stats["skipped"] += 1

            lbl_src = label_path_for(r.path)
            lbl_dst = (
                out_root / "detector" / "labels" / split / Path(name).with_suffix(".txt").name
            )
            if lbl_src.exists():
                _copy(lbl_src, lbl_dst)
            else:
                # Should not happen: rebalance drops unlabelled images. Recorded
                # rather than silently written as an empty background, because
                # an empty label here would teach the model to ignore objects.
                stats["no_label"] += 1
            stats[split] += 1
            n += 1
            if progress and n % progress == 0:
                print(f"    ...{n:,} files", flush=True)
    return stats


def emit_classifier(
    plan, train: list[ImageRecord], val: list[ImageRecord], out_root: Path,
    progress: int = 0,
) -> dict:
    out_root = Path(out_root)
    stats = {"train": 0, "val": 0, "copied": 0, "skipped": 0, "unassigned": 0}
    per_class: Counter = Counter()
    n = 0
    for split, recs in (("train", train), ("val", val)):
        for r in recs:
            cls = plan.assignments.get(r.path)
            if cls is None:
                stats["unassigned"] += 1
                continue
            dst = out_root / "classifier" / split / cls / Path(r.path).name
            if _copy(Path(r.path), dst):
                stats["copied"] += 1
            else:
                stats["skipped"] += 1
            stats[split] += 1
            per_class[f"{split}/{cls}"] += 1
            n += 1
            if progress and n % progress == 0:
                print(f"    ...{n:,} files", flush=True)

    cdir = out_root / "classifier"
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "classes.json").write_text(
        json.dumps(
            {
                "classes": plan.classes,
                "counts": plan.counts,
                "folded": plan.folded,
                "dropped": plan.dropped,
                "per_split": dict(sorted(per_class.items())),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return stats


def prune_unexpected(out_root: Path, expected: dict[str, set[str]]) -> dict:
    """Delete anything in the output tree that this build did not put there.

    Copies are resumable — an existing same-size destination is skipped — which
    means output from an EARLIER build survives into the new one. The first run
    of this builder had a dedup defect that destroyed whole classes; its 7,757
    stale detector images were still sitting in the tree afterwards, and
    verify() could not see the problem because those files have valid labels
    too. Only the expected set distinguishes them.

    `expected` maps a relative directory ("detector/images/train") to the set of
    filenames that belong in it. Directories absent from `expected` are ignored.
    """
    out_root = Path(out_root)
    removed = {"images": 0, "labels": 0, "dirs": 0}
    for rel, names in expected.items():
        d = out_root / rel
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if f.is_file() and f.name not in names:
                f.unlink()
                removed["labels" if f.suffix == ".txt" else "images"] += 1

    # class folders the current plan no longer contains
    for split in ("train", "val"):
        d = out_root / "classifier" / split
        if not d.is_dir():
            continue
        keep = expected.get(f"classifier/{split}/", set())
        for sub in d.iterdir():
            if sub.is_dir() and sub.name not in keep:
                shutil.rmtree(sub, ignore_errors=True)
                removed["dirs"] += 1
    return removed


def write_dataset_yaml(out_root: Path) -> Path:
    out_root = Path(out_root)
    det = (out_root / "detector").resolve()
    det.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Generated by scripts/build_dataset.py - do not edit by hand.",
        "# Deduplicated, rare-class-preserving, leak-free split.",
        "",
        f"path: {det.as_posix()}",
        "train: images/train",
        "val: images/val",
        "",
        f"nc: {NUM_COARSE}",
        "names:",
    ]
    lines += [f"  {i}: {n}" for i, n in enumerate(COARSE_NAMES)]
    p = det / "dataset.yaml"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def verify(out_root: Path, expected_counts: dict[str, int] | None = None) -> list[str]:
    """Return a list of integrity problems; empty means healthy.

    expected_counts maps a relative dir to how many files should be in it. Pass
    it: per-file checks alone cannot detect stale output from an earlier build,
    because those files are individually valid — only the count gives it away.
    """
    out_root = Path(out_root)
    problems: list[str] = []
    det = out_root / "detector"
    seen: dict[str, str] = {}

    for rel, n in (expected_counts or {}).items():
        d = out_root / rel
        actual = sum(1 for f in d.iterdir() if f.is_file()) if d.is_dir() else 0
        if actual != n:
            problems.append(
                f"{rel}: expected {n:,} files, found {actual:,} "
                f"({actual - n:+,} — stale output from an earlier build?)"
            )

    for split in ("train", "val"):
        img_dir = det / "images" / split
        if not img_dir.exists():
            continue
        for img in img_dir.iterdir():
            if not img.is_file():
                continue
            lbl = det / "labels" / split / img.with_suffix(".txt").name
            if not lbl.exists():
                problems.append(f"missing label for {split}/{img.name}")
                continue
            for row in lbl.read_text(encoding="utf-8").splitlines():
                parts = row.split()
                if not parts:
                    continue
                try:
                    cid = int(parts[0])
                except ValueError:
                    problems.append(f"malformed row in {split}/{lbl.name}: {row[:40]!r}")
                    continue
                if not (0 <= cid < NUM_COARSE):
                    problems.append(f"class id {cid} out of range in {split}/{lbl.name}")
            if img.name in seen and seen[img.name] != split:
                problems.append(f"{img.name} present in both train and val")
            seen[img.name] = split

    cls_root = out_root / "classifier"
    if cls_root.exists():
        tr = {d.name for d in (cls_root / "train").iterdir()} if (cls_root / "train").exists() else set()
        va = {d.name for d in (cls_root / "val").iterdir()} if (cls_root / "val").exists() else set()
        for missing in sorted(tr - va):
            problems.append(f"classifier class {missing!r} has train but no val split")
        for empty in sorted(c for c in tr if not any((cls_root / "train" / c).iterdir())):
            problems.append(f"classifier class {empty!r} train folder is empty")

    return problems
