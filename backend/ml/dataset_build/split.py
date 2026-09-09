"""Stage 5 — leak-free, group-aware train/val split.

This is orthogonal to Stage 2 dedup and BOTH are required:

  * grouping (here) catches near-identical images that share a filename
    lineage — Roboflow augmentations of one source, consecutive frames of one
    MOT/VIRAT clip. They are different pictures, so their hashes differ, but
    putting them on opposite sides still leaks.
  * dHash dedup (stage 2) catches images that are pixel-identical but share no
    naming relationship — the same aircraft photo saved twice under unrelated
    names, which is the dominant pattern in cropped_classes.

Neither subsumes the other.
"""

from __future__ import annotations

import os
from collections import defaultdict

from ml.dataset_build.index import ImageRecord
from ml.grouping import family, group_key, stable_bucket


def split_records(
    records: list[ImageRecord], val_fraction: float = 0.1, seed: int = 42
) -> tuple[list[ImageRecord], list[ImageRecord]]:
    """Partition by group key, stratified per source family, deterministically."""
    by_family: dict[str, dict[str, list[ImageRecord]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for r in records:
        name = os.path.basename(r.path)
        by_family[family(name)][group_key(name)].append(r)

    train: list[ImageRecord] = []
    val: list[ImageRecord] = []
    for _fam, groups in sorted(by_family.items()):
        keys = sorted(groups)
        picked = {k for k in keys if stable_bucket(k, seed) < val_fraction}
        # A family whose groups all hash high would contribute nothing to val,
        # leaving that source unrepresented; force its lowest-hashing group in.
        if keys and not picked:
            picked = {min(keys, key=lambda k: stable_bucket(k, seed))}
        for k in keys:
            (val if k in picked else train).extend(groups[k])

    train.sort(key=lambda r: r.path)
    val.sort(key=lambda r: r.path)
    return train, val


def assert_no_leak(train: list[ImageRecord], val: list[ImageRecord]) -> None:
    """Raise if any group straddles the split. Cheap, and the whole point."""
    tk = {group_key(os.path.basename(r.path)) for r in train}
    vk = {group_key(os.path.basename(r.path)) for r in val}
    shared = tk & vk
    if shared:
        raise AssertionError(
            f"LEAK: {len(shared)} group(s) on both sides, e.g. {sorted(shared)[:3]}"
        )
