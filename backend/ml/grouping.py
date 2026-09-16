"""Leak-safe grouping keys for train/val splitting.

Extracted from scripts/make_clean_split.py so that script and
ml.dataset_build.split share one implementation rather than two that can drift.

Two images belong to the same group when they are twins of one source:
  * Roboflow augmentations  -> strip `.rf.<hash>`      (`<id>_jpg.rf.<hash>.jpg`)
  * MOT / VIRAT frames      -> strip the trailing `_<frame>` to get a clip id
                               (only for our own `mot_` / `virat_` prefixes)

A group never straddles the train/val boundary, so near-twins cannot inflate
validation scores.
"""

from __future__ import annotations

import hashlib
import os
import re

IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
RF_HASH = re.compile(r"\.rf\.[0-9a-fA-F]{6,}\.(?:jpg|jpeg|png|bmp|webp)$", re.I)
# our own frame-sequence prefixes (from convert_mot17_to_yolo / convert_virat)
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
    h = hashlib.md5(f"{seed}:{key}".encode(), usedforsecurity=False).hexdigest()  # deterministic split bucket
    return int(h[:8], 16) / 0xFFFFFFFF
