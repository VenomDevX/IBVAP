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
from collections.abc import Callable

from ml.dataset_build.index import ImageRecord

BANDS = 4
BAND_BITS = 16
BAND_MASK = (1 << BAND_BITS) - 1


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def _make_rank(priority: Callable[[ImageRecord], int]):
    """Preference for the surviving representative of a duplicate group.

    Caller priority FIRST (higher wins), then largest pixel area, then largest
    file, then path for a stable tiebreak independent of input ordering.

    Priority is not decoration. In this corpus the aggregate folders are
    byte-identical copies of their children — Two_Wheeler IS Bicycle+Motorcycle,
    Animal IS Dog+Bird+Cat+Horse+Sheep+Cow, to the image. Ranking on path alone
    let "Animal/x.jpg" beat "Animals/Dog/x.jpg" and "Two_Wheeler/" beat
    "Vehicles/Bicycle/" purely on alphabetical order, keeping the unlabelled
    aggregate copy and destroying the specifically-labelled one. That silently
    zeroed Bicycle, Motorcycle, Dog, Cat, Cow, Horse, Bird and Sheep.
    """

    def _rank(r: ImageRecord) -> tuple:
        return (-priority(r), -(r.width * r.height), -r.size, r.path)

    return _rank


def _near_pass(
    survivors: list[ImageRecord], max_distance: int, emit
) -> list[ImageRecord]:
    """Multi-index-hashing near-duplicate pass over one already-ranked group."""
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
            emit(r.path, match.path, "near")
            continue
        pos = len(kept)
        kept.append(r)
        for i, b in enumerate(bands):
            band_index[i][b].append(pos)

    return kept


def dedup(
    records: list[ImageRecord],
    max_distance: int = 3,
    priority: Callable[[ImageRecord], int] | None = None,
    group_by: Callable[[ImageRecord], str] | None = None,
    conflict_key: Callable[[ImageRecord], str] | None = None,
    on_removed: Callable[[str, str, str], None] | None = None,
) -> tuple[list[ImageRecord], list[tuple[str, str, str]]]:
    """Return (kept, removed) where removed is (dropped_path, kept_path, reason).

    priority — higher-scoring records win duplicate ties. Use it to keep the
    more informative copy (a specific class over an aggregate, a rare-class
    detector image over a person-only one).

    group_by — when given, the NEAR pass only compares records sharing a key.
    For classifier crops pass the resolved class: a near-duplicate within one
    class is redundancy worth removing, but two visually similar images in
    DIFFERENT classes are two different labels, and dropping one destroys the
    very distinction the classifier exists to learn. The exact (md5) pass stays
    global — byte-identical files really are one file, whatever folder they sit
    in — and `priority` decides which copy survives.

    conflict_key — when given, an exact-duplicate group whose top-priority
    members disagree on this key is DROPPED ENTIRELY (reason 'conflict')
    rather than resolved arbitrarily. Use the class: identical bytes under two
    different labels mean at least one label is wrong.

    on_removed — when given, each removal is streamed to this callback and the
    returned `removed` list stays empty. The full corpus produces ~365k
    removals, each holding two long path strings; accumulating them alongside
    677k records is what pushed the build into an OS out-of-memory kill.
    """
    prio = priority or (lambda _r: 0)
    _rank = _make_rank(prio)
    removed: list[tuple[str, str, str]] = []
    emit = on_removed if on_removed is not None else (
        lambda a, b, c: removed.append((a, b, c))
    )

    # ---- pass 1: exact, by md5 (always global) ----
    by_md5: dict[str, list[ImageRecord]] = defaultdict(list)
    for r in records:
        by_md5[r.md5].append(r)
    survivors: list[ImageRecord] = []
    for group in by_md5.values():
        group.sort(key=_rank)

        # Byte-identical files carrying DIFFERENT class labels are not
        # duplicates, they are corrupt data. This corpus has 3,090 of them:
        # every Forklift image is also filed as Car, every Bus image is also
        # filed as Car. Whichever copy survives would be decided by alphabetical
        # order — a coin flip that can teach the classifier a forklift is a car.
        # Aggregates are exempt: they lose on priority before we get here, so a
        # child-vs-aggregate pair is a duplicate, not a conflict.
        if conflict_key is not None:
            top = prio(group[0])
            contenders = {conflict_key(r) for r in group if prio(r) == top}
            if len(contenders) > 1:
                for r in group:
                    emit(r.path, "", "conflict")
                continue

        survivors.append(group[0])
        for dup in group[1:]:
            emit(dup.path, group[0].path, "exact")

    survivors.sort(key=_rank)  # best representatives get indexed first
    if max_distance <= 0:
        return survivors, removed

    # ---- pass 2: near, per group ----
    if group_by is None:
        return _near_pass(survivors, max_distance, emit), removed

    buckets: dict[str, list[ImageRecord]] = defaultdict(list)
    for r in survivors:
        buckets[group_by(r)].append(r)

    survivors.clear()  # buckets hold the only references we still need
    kept = []
    for key in sorted(buckets):
        kept.extend(_near_pass(buckets.pop(key), max_distance, emit))
    kept.sort(key=_rank)
    return kept, removed
