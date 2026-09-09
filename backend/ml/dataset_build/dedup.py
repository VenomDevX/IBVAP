"""Stage 2 — remove exact and near-duplicate images.

Runs BEFORE any train/val split, which is the whole point. A 33,478-image
sample of data/cropped_classes measured 14.5% byte-identical and 17.7%
near-duplicate images, concentrated in exactly the classes that can least
afford it (P3 20.1%, WZ7 21.6%, Su57 18.6%, AH64 18.6%). Splitting first
places identical images on both sides and inflates validation accuracy —
the model is scored on pictures it trained on.

Performance: comparing 557k hashes pairwise is 1.5e11 operations. Instead we
use multi-index hashing — split each 64-bit dHash into four 16-bit bands. Two
hashes within Hamming distance 3 must agree exactly on at least one band
(pigeonhole: 4 bands, at most 3 differing bits, so some band has zero). Bucket
by band and compare only within buckets. Exact for distance <= 3, and roughly
linear in practice.
"""

from __future__ import annotations

from collections import defaultdict

from ml.dataset_build.index import ImageRecord

BANDS = 4
BAND_BITS = 16
BAND_MASK = (1 << BAND_BITS) - 1


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def _rank(r: ImageRecord) -> tuple:
    """Preference for the surviving representative of a duplicate group.

    Largest pixel area first, then largest file, then path for a stable
    tiebreak so the result does not depend on input ordering.
    """
    return (-(r.width * r.height), -r.size, r.path)


def dedup(
    records: list[ImageRecord], max_distance: int = 3
) -> tuple[list[ImageRecord], list[tuple[str, str, str]]]:
    """Return (kept, removed) where removed is (dropped_path, kept_path, reason)."""
    removed: list[tuple[str, str, str]] = []

    # ---- pass 1: exact, by md5 ----
    by_md5: dict[str, list[ImageRecord]] = defaultdict(list)
    for r in records:
        by_md5[r.md5].append(r)
    survivors: list[ImageRecord] = []
    for group in by_md5.values():
        group.sort(key=_rank)
        survivors.append(group[0])
        for dup in group[1:]:
            removed.append((dup.path, group[0].path, "exact"))

    if max_distance <= 0:
        survivors.sort(key=_rank)
        return survivors, removed

    # ---- pass 2: near, by multi-index hashing on dHash ----
    survivors.sort(key=_rank)  # best representatives get indexed first
    band_index: list[dict[int, list[int]]] = [defaultdict(list) for _ in range(BANDS)]
    kept: list[ImageRecord] = []

    for r in survivors:
        bands = [(r.dhash >> (i * BAND_BITS)) & BAND_MASK for i in range(BANDS)]
        match: ImageRecord | None = None
        seen: set[int] = set()
        for i, b in enumerate(bands):
            for pos in band_index[i].get(b, ()):
                if pos in seen:
                    continue
                seen.add(pos)
                if hamming(kept[pos].dhash, r.dhash) <= max_distance:
                    match = kept[pos]
                    break
            if match is not None:
                break
        if match is not None:
            removed.append((r.path, match.path, "near"))
            continue
        pos = len(kept)
        kept.append(r)
        for i, b in enumerate(bands):
            band_index[i][b].append(pos)

    return kept, removed
