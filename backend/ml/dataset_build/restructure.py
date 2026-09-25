"""Stage 4 — turn 91 messy crop folders into a trainable class list.

Source defects this fixes:
  * Aggregate folders sitting BESIDE their own children, double-counting:
    Military_Aircraft (14,447) next to Military/F16...; Animal (7,994) next to
    Animals/Dog...; Two_Wheeler (6,716) next to Vehicles/Bicycle+Motorcycle.
    scripts/train_classifier.py carried a hardcoded skip-list for exactly these
    three; resolving them structurally is what lets that band-aid go away.
  * 43 of 91 classes under 200 images, down to KJ600 with 10.
  * Inconsistent naming: Animal vs Animals, Military vs Military_Aircraft,
    "Night Vision Object" in taxonomy vs Night_Vision_Object on disk.

Folding is not discarding. An AH64 crop below the threshold becomes training
data for `helicopter`, so the model still learns from it — just at coarse
granularity, and it answers honestly rather than guessing a type it never had
enough examples of.

Naming convention: fine classes keep their taxonomy spelling with spaces turned
into underscores (F16, Tank, Night_Vision_Object). Coarse catch-all buckets use
the lowercase coarse name (aircraft, helicopter, drone_uav). The case difference
is deliberate and load-bearing for a human reading the folder listing: lowercase
means "this is the bucket for things we could not name precisely".
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from ml.dataset_build.index import ImageRecord
from ml.taxonomy import COARSE_NAMES, FINE_NAMES, FINE_TO_COARSE

# Folders that are aggregates rather than real classes.
#   str  -> redirect every image to that class
#   None -> drop, the label is ambiguous
AGGREGATE_MAP: dict[str, str | None] = {
    # unidentified military aircraft: exactly what the `aircraft` bucket means
    "Military_Aircraft": "aircraft",
    "Generic_Jet": "aircraft",
    "Large_Military_Plane": "aircraft",
    # unidentified animal, sitting beside Animals/Dog, Animals/Bird, ...
    "Animal": "animal",
    # AMBIGUOUS: could be Bicycle or Motorcycle, and BOTH survive as named
    # classes. A third overlapping bucket would actively confuse them, so the
    # 6,716 images are dropped rather than poisoning two good classes.
    "Two_Wheeler": None,
}


def _norm(s: str) -> str:
    """Fold disk spelling and taxonomy spelling onto one key.

    'Night_Vision_Object' (folder) and 'Night Vision Object' (taxonomy) must
    resolve to the same class.
    """
    return s.strip().lower().replace(" ", "_").replace("-", "_")


_FINE_BY_NORM = {_norm(name): fid for fid, name in FINE_NAMES.items()}
_COARSE_SET = set(COARSE_NAMES)


def canonical_class_name(leaf: str) -> str | None:
    """Canonical class name for a leaf folder, or None if taxonomy doesn't know it."""
    fid = _FINE_BY_NORM.get(_norm(leaf))
    if fid is None:
        return None
    return FINE_NAMES[fid].replace(" ", "_")


def coarse_parent(class_name: str) -> str | None:
    """Coarse bucket for a fine class name, or None if unmapped."""
    fid = _FINE_BY_NORM.get(_norm(class_name))
    if fid is None:
        return None
    return COARSE_NAMES[FINE_TO_COARSE[fid]]


def leaf_of(rel: str) -> str | None:
    """Leaf folder name from an index `rel` like 'Military/F16/x.jpg' -> 'F16'."""
    parts = rel.split("/")
    if len(parts) < 2:
        return None  # image sitting at the source root: no class to infer
    return parts[-2]


def specificity(rec) -> int:
    """Dedup tie-break priority: higher wins. Specific label beats aggregate.

    The aggregate folders are byte-identical copies of their children in this
    corpus (Two_Wheeler IS Bicycle+Motorcycle image-for-image; Animal IS
    Dog+Bird+Cat+Horse+Sheep+Cow). When dedup meets that pair it must keep the
    copy that carries the specific label, or the fine class is annihilated and
    only the useless aggregate survives.
    """
    leaf = leaf_of(rec.rel)
    if leaf is None:
        return 0
    return 0 if leaf in AGGREGATE_MAP else 1


def dedup_group(rec) -> str:
    """Near-dedup grouping key: the class this crop will end up in.

    Resolves aggregates first so Two_Wheeler/x.jpg and Vehicles/Bicycle/y.jpg
    are not treated as one class before the plan is built.
    """
    leaf = leaf_of(rec.rel)
    if leaf is None:
        return "<root>"
    if leaf in AGGREGATE_MAP:
        return AGGREGATE_MAP[leaf] or "<dropped>"
    return canonical_class_name(leaf) or f"<unknown:{leaf}>"


@dataclass
class ClassPlan:
    assignments: dict[str, str] = field(default_factory=dict)  # path -> class
    classes: list[str] = field(default_factory=list)
    folded: dict[str, str] = field(default_factory=dict)  # fine -> coarse bucket
    dropped: dict[str, int] = field(default_factory=dict)  # class -> images lost
    counts: dict[str, int] = field(default_factory=dict)  # class -> images kept


def build_class_plan(records: list[ImageRecord], threshold: int = 200, cap: int = 1500, seed: int = 42) -> ClassPlan:
    plan = ClassPlan()

    # ---- 1. candidate class per record, resolving aggregates ----
    candidate: dict[str, str] = {}
    for r in records:
        leaf = leaf_of(r.rel)
        if leaf is None:
            plan.dropped["<root>"] = plan.dropped.get("<root>", 0) + 1
            continue
        if leaf in AGGREGATE_MAP:
            target = AGGREGATE_MAP[leaf]
            if target is None:
                plan.dropped[leaf] = plan.dropped.get(leaf, 0) + 1
                continue
            candidate[r.path] = target
            continue
        name = canonical_class_name(leaf)
        if name is None:
            plan.dropped[f"<unknown:{leaf}>"] = plan.dropped.get(f"<unknown:{leaf}>", 0) + 1
            continue
        candidate[r.path] = name

    # ---- 2. fold fine classes under the threshold into their coarse bucket ----
    counts = Counter(candidate.values())
    remap: dict[str, str] = {}
    for cls, n in counts.items():
        if n >= threshold or cls in _COARSE_SET:
            continue  # big enough, or already a coarse bucket
        parent = coarse_parent(cls)
        if parent is None:
            plan.dropped[cls] = n
            continue
        remap[cls] = parent
        plan.folded[cls] = parent

    resolved = {p: remap.get(c, c) for p, c in candidate.items()}

    # ---- 3. drop anything still starved after folding ----
    counts = Counter(resolved.values())
    starved = {c for c, n in counts.items() if n < threshold}
    for c in starved:
        plan.dropped[c] = counts[c]
    resolved = {p: c for p, c in resolved.items() if c not in starved}

    # ---- 4. cap per class, preferring the largest images ----
    by_path = {r.path: r for r in records}
    by_class: dict[str, list[ImageRecord]] = defaultdict(list)
    for p, c in resolved.items():
        by_class[c].append(by_path[p])

    for cls, items in by_class.items():
        items.sort(key=lambda r: (-(r.width * r.height), r.path))
        for r in items[:cap]:
            plan.assignments[r.path] = cls
        plan.counts[cls] = min(len(items), cap)

    plan.classes = sorted(plan.counts)
    return plan
