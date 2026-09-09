"""Stage 3 — choose which detector images survive into the release set.

The source split is 71.6% person boxes (353,464 of 493,887), with
military_ground_vehicle at 681 boxes (1:519) and bus at 799 (1:442), plus
15,741 empty images (14.7%, against a 1-10% norm). That distribution is why
the Colab run plateaued at mAP50 0.63 with recall 0.59 — person carries the
score and the tail drags it down.

Keeping every rare-class image while subsampling the person/car bulk raises
rare-class frequency AND halves epoch time. Those are usually opposing forces;
here one change buys both, which is what makes a ~30h budget on a 6GB laptop
GPU feasible at all.

Images with no label file at all are dropped, not treated as background —
see ml.dataset_build.index.has_label_file for why.
"""

from __future__ import annotations

import hashlib
from collections import Counter

from ml.dataset_build.index import ImageRecord
from ml.taxonomy import COARSE_ID

# Never subsampled. Every one of these is scarce enough that dropping any image
# measurably costs recall on a class the surveillance logic actually acts on.
RARE_CLASS_NAMES = (
    "military_ground_vehicle",  # 681 boxes, 1:519
    "bus",  # 799, 1:442
    "helicopter",  # 1,642, 1:215
    "motorcycle",  # 1,945, 1:182
    "truck",  # 1,973, 1:179
    "bicycle",  # 4,151, 1:85
    "drone_uav",  # 4,240, 1:83
    "animal",  # 7,153, 1:49
)
RARE_CLASS_IDS = frozenset(COARSE_ID[n] for n in RARE_CLASS_NAMES)


def _jitter(path: str, seed: int) -> float:
    """Stable per-path pseudo-random value; keeps selection order-independent."""
    h = hashlib.md5(f"{seed}:{path}".encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def select_detector_images(
    records: list[ImageRecord],
    labels: dict[str, list[int]],
    target: int = 50000,
    background_frac: float = 0.05,
    seed: int = 42,
    labelled: set[str] | None = None,
) -> tuple[list[ImageRecord], dict]:
    """Pick ~target detector images, preserving every rare-class instance.

    labels    — path -> class ids of its boxes ([] for a background image)
    labelled  — paths that HAVE a label file; when given, records outside it are
                dropped as lost annotations rather than kept as backgrounds.
    """
    rare: list[ImageRecord] = []
    common: list[ImageRecord] = []
    empty: list[ImageRecord] = []
    n_unlabelled = 0

    for r in records:
        if labelled is not None and r.path not in labelled:
            n_unlabelled += 1
            continue
        cls = labels.get(r.path, [])
        if not cls:
            empty.append(r)
        elif RARE_CLASS_IDS & set(cls):
            rare.append(r)
        else:
            common.append(r)

    # 1. every rare-class image, unconditionally — even past target
    selected = list(rare)

    # 2. fill toward target with the most informative common images:
    #    more boxes first, then larger, then a stable seeded tiebreak
    remaining = max(0, target - len(selected))
    common.sort(
        key=lambda r: (
            -len(labels.get(r.path, [])),
            -(r.width * r.height),
            _jitter(r.path, seed),
        )
    )
    selected.extend(common[:remaining])

    # 3. backgrounds last, capped as a fraction OF THE FINAL SET.
    #    n/(len+n) = frac  =>  n = frac*len/(1-frac)
    n_bg = int(background_frac * len(selected) / max(1e-9, 1.0 - background_frac))
    empty.sort(key=lambda r: _jitter(r.path, seed))
    selected.extend(empty[:n_bg])

    selected.sort(key=lambda r: r.path)

    boxes: Counter = Counter()
    for r in selected:
        boxes.update(labels.get(r.path, []))
    n_bg_kept = min(n_bg, len(empty))
    stats = {
        "n_selected": len(selected),
        "n_rare_kept": len(rare),
        "n_common_kept": min(remaining, len(common)),
        "n_background_kept": n_bg_kept,
        "background_pct": round(100 * n_bg_kept / max(1, len(selected)), 2),
        "n_dropped_unlabelled": n_unlabelled,
        "boxes_per_class": {int(k): v for k, v in sorted(boxes.items())},
        "available": {"rare": len(rare), "common": len(common), "empty": len(empty)},
    }
    return selected, stats
