# Local Training Dataset Rebuild — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `backend/data/` into a clean, deduplicated, class-balanced `backend/data/dataset/`, then train a YOLO coarse detector and an EfficientNetV2 fine classifier on an RTX 4050 (6 GB) inside a ~30 h budget, with every long step resumable.

**Architecture:** A six-stage builder package under `backend/ml/dataset_build/`, each stage a pure, independently testable module, driven by a thin CLI in `backend/scripts/build_dataset.py` that writes per-stage completion markers so re-runs skip finished work. Training scripts read the emitted dataset and checkpoint every epoch.

**Tech Stack:** Python 3.11, ultralytics 8.4.x, PyTorch + torchvision, timm ≥1.0, Pillow, pytest. Windows/PowerShell host, NTFS.

**Spec:** `docs/superpowers/specs/2026-09-09-local-training-dataset-rebuild-design.md`

## Global Constraints

- **Prune floor:** 200 **unique** (post-dedup) images per fine class. Yields 31 fine classes (14 civilian + 17 military).
- **Per-class cap:** 1,500 images.
- **Detector target:** ~50,000 images (`--target-detector`, default 50000).
- **Background cap:** empty (label-less) images capped at **5%** of the final detector set.
- **Detector resolution:** `imgsz=640`, `batch=8` **explicit — never `-1`**.
- **Classifier resolution:** 224px, batch 64.
- **Seed:** 42 everywhere. `val_fraction=0.1`.
- **Near-dup threshold:** dHash Hamming distance **≤ 3**.
- **Rare classes never subsampled:** `military_ground_vehicle`, `bus`, `helicopter`, `truck`, `motorcycle`, `drone_uav`, `animal`, `bicycle`.
- **Ambiguous aggregate dropped:** `Two_Wheeler` (6,716 images) — conflicts with the surviving `Bicycle` and `Motorcycle` classes. `Military_Aircraft` → `aircraft`, `Animal` → `animal`.
- **Non-destructive:** the build never modifies or deletes anything under `data/detector_yolo`, `data/unified_yolo`, `data/cropped_classes`, or the tar. Disposal is a separate opt-in script.
- **Class names:** exactly the strings in `backend/ml/taxonomy.py` (`FINE_NAMES`, `COARSE_NAMES`). No third naming scheme.
- All new code must pass the repo's existing `ruff` config (`backend/ruff.toml`).

---

## File Structure

**Create:**
- `backend/ml/grouping.py` — leak-safe grouping keys (extracted from `scripts/make_clean_split.py`, which currently owns them)
- `backend/ml/dataset_build/__init__.py`
- `backend/ml/dataset_build/index.py` — Stage 1: scan, hash, label helpers
- `backend/ml/dataset_build/dedup.py` — Stage 2: exact + near duplicate removal
- `backend/ml/dataset_build/rebalance.py` — Stage 3: detector image selection
- `backend/ml/dataset_build/restructure.py` — Stage 4: classifier class plan
- `backend/ml/dataset_build/split.py` — Stage 5: group-aware train/val split
- `backend/ml/dataset_build/emit.py` — Stage 6: copy, write configs, verify
- `backend/scripts/build_dataset.py` — CLI orchestrator with stage markers
- `backend/scripts/cleanup_data.py` — opt-in disposal
- `backend/scripts/run_training.ps1` — crash-restart wrapper
- `backend/tests/test_dataset_build.py` — fixture-based tests
- `docs/RUNBOOK_LOCAL_TRAINING.md` — exact terminal commands

**Modify:**
- `backend/scripts/make_clean_split.py` — import grouping helpers from `ml.grouping` instead of defining them
- `backend/scripts/train_yolo.py` — new defaults (640/8), benchmark mode
- `backend/scripts/train_classifier.py` — full rewrite
- `backend/.gitignore` (or repo root) — ignore `backend/data/dataset/`

---

## Task 1: Grouping helpers extracted to `ml.grouping`

`scripts/make_clean_split.py` already owns the leak-safe grouping logic. The builder needs it too, and importing from a script directory is fragile. Extract, keep behaviour identical.

**Files:**
- Create: `backend/ml/grouping.py`
- Modify: `backend/scripts/make_clean_split.py`
- Test: `backend/tests/test_dataset_build.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `source_key(filename: str) -> str`
  - `group_key(filename: str) -> str`
  - `family(filename: str) -> str`
  - `stable_bucket(key: str, seed: int) -> float`

- [ ] **Step 1: Read the current implementation**

Run: `sed -n '40,75p' backend/scripts/make_clean_split.py`

Copy the four functions verbatim — do not rewrite the regexes. They encode
Roboflow (`.rf.<hash>`) and MOT/VIRAT (`_<frame>`) conventions that are already
proven against this data.

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_dataset_build.py
from ml.grouping import group_key, stable_bucket, family


def test_group_key_strips_roboflow_hash():
    a = group_key("frame_001_jpg.rf.abc123def456.jpg")
    b = group_key("frame_001_jpg.rf.999888777666.jpg")
    assert a == b, "roboflow twins must share a group"


def test_group_key_strips_mot_frame_number():
    a = group_key("MOT17-02_000123.jpg")
    b = group_key("MOT17-02_000124.jpg")
    assert a == b, "frames of one clip must share a group"


def test_group_key_separates_different_clips():
    assert group_key("MOT17-02_000123.jpg") != group_key("MOT17-04_000123.jpg")


def test_stable_bucket_is_deterministic():
    assert stable_bucket("abc", 42) == stable_bucket("abc", 42)
    assert 0.0 <= stable_bucket("abc", 42) < 1.0


def test_stable_bucket_varies_with_seed():
    assert stable_bucket("abc", 42) != stable_bucket("abc", 43)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_dataset_build.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ml.grouping'`

- [ ] **Step 4: Create `ml/grouping.py`**

Move the four functions and their module-level regex constants out of
`make_clean_split.py` into `backend/ml/grouping.py`, adding a module docstring:

```python
"""Leak-safe grouping keys for train/val splitting.

Extracted from scripts/make_clean_split.py so both that script and
ml.dataset_build.split share one implementation.

Two images belong to the same group when they are twins of one source:
  * Roboflow augmentations  -> strip `.rf.<hash>`
  * MOT / VIRAT frames      -> strip the trailing `_<frame>` to get a clip id
Groups never straddle the train/val boundary.
"""
```

- [ ] **Step 5: Update `make_clean_split.py` to import them**

Delete the four function bodies and their regex constants from the script;
add near the other imports:

```python
from ml.grouping import family, group_key, source_key, stable_bucket
```

Leave every call site unchanged.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_dataset_build.py -v`
Expected: 5 passed

- [ ] **Step 7: Verify the existing script still runs**

Run: `cd backend && python scripts/make_clean_split.py --help`
Expected: usage text, no ImportError.

- [ ] **Step 8: Commit**

```bash
git add backend/ml/grouping.py backend/scripts/make_clean_split.py backend/tests/test_dataset_build.py
git commit -m "refactor(ml): extract leak-safe grouping helpers into ml.grouping"
```

---

## Task 2: Stage 1 — index

Walks the source trees once and records everything downstream needs. This is the
only full pass over source data.

**Files:**
- Create: `backend/ml/dataset_build/__init__.py`, `backend/ml/dataset_build/index.py`
- Test: `backend/tests/test_dataset_build.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `@dataclass(frozen=True) ImageRecord` with fields `path: str`, `source: str`, `rel: str`, `width: int`, `height: int`, `size: int`, `md5: str`, `dhash: int`
  - `dhash(path: str | Path, size: int = 8) -> int`
  - `label_path_for(img_path: str) -> Path`
  - `read_label_classes(img_path: str) -> list[int]`
  - `scan_tree(root: Path, source: str) -> Iterator[ImageRecord]`
  - `write_index(records: Iterable[ImageRecord], out: Path) -> int`
  - `read_index(path: Path) -> list[ImageRecord]`

- [ ] **Step 1: Write the failing test**

```python
import json
from pathlib import Path

from PIL import Image

from ml.dataset_build.index import (
    ImageRecord, dhash, label_path_for, read_index, read_label_classes,
    scan_tree, write_index,
)


def _img(path: Path, size=(32, 32), color=(10, 20, 30)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


def test_dhash_identical_images_match(tmp_path):
    a = _img(tmp_path / "a.jpg")
    b = _img(tmp_path / "b.jpg")
    assert dhash(a) == dhash(b)


def test_dhash_differs_for_different_images(tmp_path):
    a = _img(tmp_path / "a.jpg", color=(0, 0, 0))
    b = tmp_path / "b.jpg"
    Image.linear_gradient("L").convert("RGB").save(b)
    assert dhash(a) != dhash(b)


def test_label_path_for_swaps_images_dir_for_labels(tmp_path):
    p = tmp_path / "images" / "train" / "x.jpg"
    assert label_path_for(str(p)) == tmp_path / "labels" / "train" / "x.txt"


def test_read_label_classes(tmp_path):
    img = _img(tmp_path / "images" / "train" / "x.jpg")
    lbl = tmp_path / "labels" / "train" / "x.txt"
    lbl.parent.mkdir(parents=True, exist_ok=True)
    lbl.write_text("0 0.5 0.5 0.1 0.1\n7 0.2 0.2 0.1 0.1\n0 0.3 0.3 0.1 0.1\n")
    assert read_label_classes(str(img)) == [0, 7, 0]


def test_read_label_classes_missing_file_is_empty(tmp_path):
    img = _img(tmp_path / "images" / "train" / "y.jpg")
    assert read_label_classes(str(img)) == []


def test_scan_tree_records_dimensions_and_hashes(tmp_path):
    _img(tmp_path / "images" / "train" / "a.jpg", size=(64, 48))
    recs = list(scan_tree(tmp_path, "detector"))
    assert len(recs) == 1
    r = recs[0]
    assert r.width == 64 and r.height == 48
    assert len(r.md5) == 32
    assert r.source == "detector"
    assert r.rel.replace("\\", "/") == "images/train/a.jpg"


def test_index_roundtrip(tmp_path):
    _img(tmp_path / "images" / "train" / "a.jpg")
    recs = list(scan_tree(tmp_path, "detector"))
    out = tmp_path / "index.jsonl"
    assert write_index(recs, out) == 1
    back = read_index(out)
    assert back == recs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_dataset_build.py -v -k "dhash or label or scan or index"`
Expected: FAIL — `ModuleNotFoundError: No module named 'ml.dataset_build'`

- [ ] **Step 3: Implement `ml/dataset_build/index.py`**

```python
"""Stage 1 — index every source image once.

Everything downstream reads this index rather than re-walking the tree.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@dataclass(frozen=True)
class ImageRecord:
    path: str
    source: str          # "detector" | "crops"
    rel: str             # path relative to its source root, forward slashes
    width: int
    height: int
    size: int
    md5: str
    dhash: int


def dhash(path: str | Path, size: int = 8) -> int:
    """64-bit difference hash. Rows of size+1 pixels -> size comparisons each."""
    with Image.open(path) as im:
        im = im.convert("L").resize((size + 1, size), Image.BILINEAR)
        px = list(im.getdata())
    bits = 0
    for r in range(size):
        row = px[r * (size + 1) : (r + 1) * (size + 1)]
        for c in range(size):
            bits = (bits << 1) | (1 if row[c] < row[c + 1] else 0)
    return bits


def label_path_for(img_path: str) -> Path:
    """YOLO convention: .../images/<split>/x.jpg -> .../labels/<split>/x.txt"""
    s = str(img_path).replace("\\", "/")
    if "/images/" in s:
        s = s.replace("/images/", "/labels/", 1)
    return Path(s).with_suffix(".txt")


def read_label_classes(img_path: str) -> list[int]:
    """Class ids of every box for an image; [] if the label file is absent/empty."""
    lp = label_path_for(img_path)
    try:
        text = lp.read_text(encoding="utf-8")
    except OSError:
        return []
    out: list[int] = []
    for row in text.splitlines():
        parts = row.split()
        if parts:
            out.append(int(parts[0]))
    return out


def scan_tree(root: Path, source: str) -> Iterator[ImageRecord]:
    root = Path(root)
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            entries = list(os.scandir(d))
        except OSError:
            continue
        for e in entries:
            if e.is_dir(follow_symlinks=False):
                stack.append(Path(e.path))
                continue
            if os.path.splitext(e.name)[1].lower() not in IMG_EXT:
                continue
            try:
                with open(e.path, "rb") as fh:
                    digest = hashlib.md5(fh.read()).hexdigest()
                with Image.open(e.path) as im:
                    w, h = im.size
                dh = dhash(e.path)
            except Exception:
                continue    # unreadable/corrupt image: excluded, counted by caller
            yield ImageRecord(
                path=str(Path(e.path).resolve()),
                source=source,
                rel=str(Path(e.path).relative_to(root)).replace("\\", "/"),
                width=w,
                height=h,
                size=e.stat().st_size,
                md5=digest,
                dhash=dh,
            )


def write_index(records: Iterable[ImageRecord], out: Path) -> int:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(out, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(asdict(r)) + "\n")
            n += 1
    return n


def read_index(path: Path) -> list[ImageRecord]:
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(ImageRecord(**json.loads(line)))
    return out
```

Also create an empty `backend/ml/dataset_build/__init__.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_dataset_build.py -v`
Expected: all pass

- [ ] **Step 5: Smoke-test against real data**

```bash
cd backend && python -c "
from pathlib import Path
from ml.dataset_build.index import scan_tree
import itertools
r = list(itertools.islice(scan_tree(Path('data/detector_yolo'), 'detector'), 5))
for x in r: print(x.rel, x.width, x.height, x.md5[:8], hex(x.dhash))
"
```
Expected: 5 real records with plausible dimensions.

- [ ] **Step 6: Commit**

```bash
git add backend/ml/dataset_build backend/tests/test_dataset_build.py
git commit -m "feat(dataset): stage 1 index with md5 + dhash"
```

---

## Task 3: Stage 2 — dedup

Removes exact and near duplicates **before** any split. This is the fix for the
train/val leak identified in the spec §1.4.

**Files:**
- Create: `backend/ml/dataset_build/dedup.py`
- Test: `backend/tests/test_dataset_build.py`

**Interfaces:**
- Consumes: `ImageRecord` from Task 2
- Produces:
  - `hamming(a: int, b: int) -> int`
  - `dedup(records: list[ImageRecord], max_distance: int = 3) -> tuple[list[ImageRecord], list[tuple[str, str, str]]]` — returns `(kept, removed)` where each removed entry is `(dropped_path, kept_path, reason)` and `reason` is `"exact"` or `"near"`

**Performance note — this is the one place a naive implementation will hang.**
Comparing 557k hashes pairwise is 1.5e11 operations. Use **multi-index hashing**:
split the 64-bit hash into four 16-bit bands. Two hashes within Hamming distance
3 must agree exactly on at least one band (pigeonhole: 4 bands, ≤3 differing
bits ⇒ some band has zero differing bits). Bucket by band, compare only within
buckets. Exact for ≤3, and roughly linear in practice.

- [ ] **Step 1: Write the failing test**

```python
from ml.dataset_build.dedup import dedup, hamming
from ml.dataset_build.index import ImageRecord


def _rec(path, md5, dh, w=100, h=100):
    return ImageRecord(path=path, source="crops", rel=path, width=w, height=h,
                       size=w * h, md5=md5, dhash=dh)


def test_hamming():
    assert hamming(0b0000, 0b0000) == 0
    assert hamming(0b0001, 0b0000) == 1
    assert hamming(0b1011, 0b0010) == 2


def test_dedup_removes_exact_duplicates():
    recs = [_rec("a.jpg", "same", 1), _rec("b.jpg", "same", 1)]
    kept, removed = dedup(recs)
    assert len(kept) == 1
    assert len(removed) == 1
    assert removed[0][2] == "exact"


def test_dedup_keeps_highest_resolution_representative():
    recs = [_rec("small.jpg", "m1", 1, w=50, h=50),
            _rec("big.jpg", "m2", 1, w=500, h=500)]
    kept, removed = dedup(recs)
    assert len(kept) == 1
    assert kept[0].path == "big.jpg"


def test_dedup_removes_near_duplicates_within_threshold():
    # differ by 2 bits -> near duplicate
    recs = [_rec("a.jpg", "m1", 0b1100), _rec("b.jpg", "m2", 0b0000)]
    kept, removed = dedup(recs, max_distance=3)
    assert len(kept) == 1
    assert removed[0][2] == "near"


def test_dedup_keeps_images_beyond_threshold():
    # differ by 4 bits -> distinct
    recs = [_rec("a.jpg", "m1", 0b1111), _rec("b.jpg", "m2", 0b0000)]
    kept, _ = dedup(recs, max_distance=3)
    assert len(kept) == 2


def test_dedup_is_deterministic():
    recs = [_rec(f"{i}.jpg", f"m{i}", i) for i in range(50)]
    a, _ = dedup(list(recs))
    b, _ = dedup(list(reversed(recs)))
    assert {r.path for r in a} == {r.path for r in b}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_dataset_build.py -v -k dedup`
Expected: FAIL — no module `ml.dataset_build.dedup`

- [ ] **Step 3: Implement `ml/dataset_build/dedup.py`**

```python
"""Stage 2 — remove exact and near-duplicate images.

Runs BEFORE any train/val split. The source crop set carries ~14.5% exact and
~17.7% near duplicates; splitting first would place identical images on both
sides and inflate validation accuracy.
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
    """Preference for the surviving representative: bigger, then stable by path."""
    return (-(r.width * r.height), -r.size, r.path)


def dedup(
    records: list[ImageRecord], max_distance: int = 3
) -> tuple[list[ImageRecord], list[tuple[str, str, str]]]:
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

    # ---- pass 2: near, by multi-index hashing on dhash ----
    # Two hashes within Hamming<=3 must share at least one of 4 16-bit bands.
    survivors.sort(key=_rank)
    band_index: list[dict[int, list[int]]] = [defaultdict(list) for _ in range(BANDS)]
    kept: list[ImageRecord] = []
    kept_by_pos: dict[int, ImageRecord] = {}

    for r in survivors:
        bands = [(r.dhash >> (i * BAND_BITS)) & BAND_MASK for i in range(BANDS)]
        match = None
        seen: set[int] = set()
        for i, b in enumerate(bands):
            for pos in band_index[i].get(b, ()):
                if pos in seen:
                    continue
                seen.add(pos)
                if hamming(kept_by_pos[pos].dhash, r.dhash) <= max_distance:
                    match = kept_by_pos[pos]
                    break
            if match:
                break
        if match is not None:
            removed.append((r.path, match.path, "near"))
            continue
        pos = len(kept)
        kept.append(r)
        kept_by_pos[pos] = r
        for i, b in enumerate(bands):
            band_index[i][b].append(pos)

    return kept, removed
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_dataset_build.py -v -k dedup`
Expected: 6 passed

- [ ] **Step 5: Verify performance on a realistic volume**

```bash
cd backend && python -c "
import random, time
from ml.dataset_build.dedup import dedup
from ml.dataset_build.index import ImageRecord
random.seed(0)
recs=[ImageRecord(path=f'{i}.jpg',source='crops',rel=f'{i}.jpg',width=100,height=100,
      size=1000,md5=f'm{i}',dhash=random.getrandbits(64)) for i in range(200000)]
t=time.time(); kept,rm=dedup(recs); print(len(kept),len(rm),'%.1fs'%(time.time()-t))
"
```
Expected: completes in well under 60 s. If it takes minutes, the band index is
not being used — re-check Step 3.

- [ ] **Step 6: Commit**

```bash
git add backend/ml/dataset_build/dedup.py backend/tests/test_dataset_build.py
git commit -m "feat(dataset): stage 2 exact + near dedup via multi-index hashing"
```

---

## Task 4: Stage 3 — detector rebalance

Selects ~50k detector images that preserve every rare-class box while cutting
person/car redundancy and capping empty backgrounds.

**Files:**
- Create: `backend/ml/dataset_build/rebalance.py`
- Test: `backend/tests/test_dataset_build.py`

**Interfaces:**
- Consumes: `ImageRecord` (Task 2)
- Produces:
  - `RARE_CLASS_IDS: frozenset[int]`
  - `select_detector_images(records: list[ImageRecord], labels: dict[str, list[int]], target: int = 50000, background_frac: float = 0.05, seed: int = 42) -> tuple[list[ImageRecord], dict]` — returns `(selected, stats)`

Selection rules, in order:
1. Every image containing **any** rare class id is kept unconditionally.
2. Remaining non-empty images (person/car only) are sorted by a deterministic
   seeded key and taken until `target` is reached, preferring images with more
   boxes and higher resolution.
3. Empty images are added last, capped at `background_frac` of the final count.

- [ ] **Step 1: Write the failing test**

```python
from ml.dataset_build.index import ImageRecord
from ml.dataset_build.rebalance import RARE_CLASS_IDS, select_detector_images


def _r(path, w=640, h=640):
    return ImageRecord(path=path, source="detector", rel=path, width=w, height=h,
                       size=w * h, md5=path, dhash=hash(path) & 0xFFFFFFFFFFFFFFFF)


def test_rare_class_ids_match_spec():
    # military_ground_vehicle, bus, helicopter, truck, motorcycle, drone_uav, animal, bicycle
    assert RARE_CLASS_IDS == frozenset({7, 2, 9, 3, 4, 10, 12, 5})


def test_every_rare_image_is_kept_even_when_over_target():
    recs = [_r(f"rare{i}.jpg") for i in range(100)]
    labels = {r.path: [7] for r in recs}
    sel, stats = select_detector_images(recs, labels, target=10, background_frac=0.0)
    assert len(sel) == 100, "rare-class images must never be dropped"


def test_person_only_images_are_subsampled():
    rare = [_r("rare.jpg")]
    person = [_r(f"p{i}.jpg") for i in range(1000)]
    labels = {"rare.jpg": [7]}
    labels.update({r.path: [0] for r in person})
    sel, stats = select_detector_images(rare + person, labels, target=101,
                                        background_frac=0.0)
    assert len(sel) == 101
    assert "rare.jpg" in {r.path for r in sel}


def test_backgrounds_capped_at_fraction():
    common = [_r(f"c{i}.jpg") for i in range(90)]
    empty = [_r(f"e{i}.jpg") for i in range(500)]
    labels = {r.path: [0] for r in common}
    labels.update({r.path: [] for r in empty})
    sel, stats = select_detector_images(common + empty, labels, target=90,
                                        background_frac=0.05)
    n_empty = sum(1 for r in sel if not labels[r.path])
    assert n_empty <= round(0.05 * len(sel)) + 1
    assert n_empty > 0, "some background is wanted, just not 14.7%"


def test_selection_is_deterministic():
    recs = [_r(f"p{i}.jpg") for i in range(200)]
    labels = {r.path: [0] for r in recs}
    a, _ = select_detector_images(recs, labels, target=50, seed=42)
    b, _ = select_detector_images(list(reversed(recs)), labels, target=50, seed=42)
    assert {r.path for r in a} == {r.path for r in b}


def test_stats_reports_per_class_boxes():
    recs = [_r("a.jpg"), _r("b.jpg")]
    labels = {"a.jpg": [0, 0, 7], "b.jpg": [2]}
    sel, stats = select_detector_images(recs, labels, target=10, background_frac=0.0)
    assert stats["boxes_per_class"][0] == 2
    assert stats["boxes_per_class"][7] == 1
    assert stats["boxes_per_class"][2] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_dataset_build.py -v -k "rare or person_only or background or selection or stats_reports"`
Expected: FAIL — no module `ml.dataset_build.rebalance`

- [ ] **Step 3: Implement `ml/dataset_build/rebalance.py`**

```python
"""Stage 3 — choose which detector images survive into the release set.

The source set is 71.6% person boxes with military_ground_vehicle at 1:519 and
14.7% empty images. Keeping every rare-class image while subsampling the
person/car bulk raises rare-class frequency and halves epoch time at once.
"""

from __future__ import annotations

import hashlib
from collections import Counter

from ml.dataset_build.index import ImageRecord
from ml.taxonomy import COARSE_ID

RARE_CLASS_NAMES = (
    "military_ground_vehicle",
    "bus",
    "helicopter",
    "truck",
    "motorcycle",
    "drone_uav",
    "animal",
    "bicycle",
)
RARE_CLASS_IDS = frozenset(COARSE_ID[n] for n in RARE_CLASS_NAMES)


def _jitter(path: str, seed: int) -> float:
    h = hashlib.md5(f"{seed}:{path}".encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def select_detector_images(
    records: list[ImageRecord],
    labels: dict[str, list[int]],
    target: int = 50000,
    background_frac: float = 0.05,
    seed: int = 42,
) -> tuple[list[ImageRecord], dict]:
    rare: list[ImageRecord] = []
    common: list[ImageRecord] = []
    empty: list[ImageRecord] = []

    for r in records:
        cls = labels.get(r.path, [])
        if not cls:
            empty.append(r)
        elif RARE_CLASS_IDS & set(cls):
            rare.append(r)
        else:
            common.append(r)

    # Rare images are never dropped.
    selected = list(rare)

    # Fill toward target with the most informative common images:
    # more boxes first, then larger, then a stable seeded tiebreak.
    remaining = max(0, target - len(selected))
    common.sort(
        key=lambda r: (
            -len(labels.get(r.path, [])),
            -(r.width * r.height),
            _jitter(r.path, seed),
        )
    )
    selected.extend(common[:remaining])

    # Backgrounds last, capped as a fraction of the final set.
    n_bg = int(background_frac * len(selected) / max(1e-9, 1 - background_frac))
    empty.sort(key=lambda r: _jitter(r.path, seed))
    selected.extend(empty[:n_bg])

    selected.sort(key=lambda r: r.path)

    boxes = Counter()
    for r in selected:
        boxes.update(labels.get(r.path, []))
    stats = {
        "n_selected": len(selected),
        "n_rare_kept": len(rare),
        "n_common_kept": min(remaining, len(common)),
        "n_background_kept": min(n_bg, len(empty)),
        "boxes_per_class": dict(boxes),
        "source_counts": {"rare": len(rare), "common": len(common), "empty": len(empty)},
    }
    return selected, stats
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_dataset_build.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add backend/ml/dataset_build/rebalance.py backend/tests/test_dataset_build.py
git commit -m "feat(dataset): stage 3 rare-preserving detector rebalance"
```

---

## Task 5: Stage 4 — classifier restructure

Resolves the aggregate/child overlap, prunes starved classes into their coarse
parent, and caps the survivors.

**Files:**
- Create: `backend/ml/dataset_build/restructure.py`
- Test: `backend/tests/test_dataset_build.py`

**Interfaces:**
- Consumes: `ImageRecord` (Task 2)
- Produces:
  - `AGGREGATE_MAP: dict[str, str | None]` — `{"Military_Aircraft": "aircraft", "Animal": "animal", "Two_Wheeler": None}` (`None` = drop as ambiguous)
  - `@dataclass ClassPlan` with `assignments: dict[str, str]`, `classes: list[str]`, `folded: dict[str, str]`, `dropped: dict[str, int]`, `counts: dict[str, int]`
  - `build_class_plan(records: list[ImageRecord], threshold: int = 200, cap: int = 1500, seed: int = 42) -> ClassPlan`

Rules:
1. Leaf folder name is the candidate class. `AGGREGATE_MAP` redirects the three
   aggregate folders; `Two_Wheeler` maps to `None` and is dropped, because both
   `Bicycle` and `Motorcycle` survive as named classes and a third overlapping
   bucket would confuse them.
2. Classes with `< threshold` records fold into their coarse parent via
   `FINE_TO_COARSE` / `COARSE_NAMES`.
3. After folding, any resulting class still under `threshold` is dropped.
4. Each surviving class is capped at `cap`, preferring the largest images.

- [ ] **Step 1: Write the failing test**

```python
from ml.dataset_build.index import ImageRecord
from ml.dataset_build.restructure import AGGREGATE_MAP, build_class_plan


def _c(cls, i, w=100):
    p = f"{cls}/{i}.jpg"
    return ImageRecord(path=p, source="crops", rel=p, width=w, height=w,
                       size=w * w, md5=p, dhash=i)


def test_aggregate_map_drops_ambiguous_two_wheeler():
    assert AGGREGATE_MAP["Military_Aircraft"] == "aircraft"
    assert AGGREGATE_MAP["Animal"] == "animal"
    assert AGGREGATE_MAP["Two_Wheeler"] is None


def test_class_above_threshold_survives():
    recs = [_c("Military/F16", i) for i in range(250)]
    plan = build_class_plan(recs, threshold=200)
    assert "F16" in plan.classes


def test_class_below_threshold_folds_into_coarse_parent():
    recs = [_c("Military/AH64", i) for i in range(50)]
    recs += [_c("Military/Mi24", i) for i in range(200)]
    plan = build_class_plan(recs, threshold=200)
    assert "AH64" not in plan.classes
    assert plan.folded["AH64"] == "helicopter"
    assert plan.assignments["Military/AH64/0.jpg"] == "helicopter"


def test_two_wheeler_images_are_dropped():
    recs = [_c("Two_Wheeler", i) for i in range(500)]
    plan = build_class_plan(recs, threshold=200)
    assert "Two_Wheeler" not in plan.classes
    assert plan.dropped["Two_Wheeler"] == 500
    assert not any(k.startswith("Two_Wheeler/") for k in plan.assignments)


def test_military_aircraft_aggregate_becomes_aircraft():
    recs = [_c("Military_Aircraft", i) for i in range(300)]
    plan = build_class_plan(recs, threshold=200)
    assert plan.assignments["Military_Aircraft/0.jpg"] == "aircraft"


def test_cap_limits_class_size_preferring_large_images():
    recs = [_c("People/Person", i, w=10 + i) for i in range(300)]
    plan = build_class_plan(recs, threshold=10, cap=100)
    assigned = [k for k, v in plan.assignments.items() if v == "Person"]
    assert len(assigned) == 100
    assert "People/Person/299.jpg" in assigned   # largest kept
    assert "People/Person/0.jpg" not in assigned  # smallest dropped


def test_plan_is_deterministic():
    recs = [_c("Military/F16", i) for i in range(400)]
    a = build_class_plan(list(recs), threshold=200, cap=250, seed=42)
    b = build_class_plan(list(reversed(recs)), threshold=200, cap=250, seed=42)
    assert a.assignments == b.assignments
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_dataset_build.py -v -k "aggregate or threshold or two_wheeler or cap_limits or plan_is"`
Expected: FAIL — no module `ml.dataset_build.restructure`

- [ ] **Step 3: Implement `ml/dataset_build/restructure.py`**

```python
"""Stage 4 — turn 91 messy crop folders into a trainable class list.

Source defects handled here:
  * aggregate folders sitting beside their own children (double counting)
  * 43 of 91 classes under 200 images
  * inconsistent naming (Animal vs Animals, Military vs Military_Aircraft)

Folding is not discarding: an AH64 crop below the threshold becomes training
data for `helicopter`, so the model still learns from it at coarse granularity.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from ml.dataset_build.index import ImageRecord
from ml.taxonomy import COARSE_NAMES, FINE_NAMES, FINE_TO_COARSE

# Aggregate folders that sit beside their own children.
# None => ambiguous, drop: Two_Wheeler cannot be resolved to Bicycle or
# Motorcycle, and both of those survive as named classes.
AGGREGATE_MAP: dict[str, str | None] = {
    "Military_Aircraft": "aircraft",
    "Animal": "animal",
    "Two_Wheeler": None,
}

_FINE_BY_NAME = {name: fid for fid, name in FINE_NAMES.items()}


@dataclass
class ClassPlan:
    assignments: dict[str, str] = field(default_factory=dict)
    classes: list[str] = field(default_factory=list)
    folded: dict[str, str] = field(default_factory=dict)
    dropped: dict[str, int] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)


def _coarse_parent(leaf: str) -> str:
    """Coarse class name for a fine leaf, or 'unknown' if unmapped."""
    fid = _FINE_BY_NAME.get(leaf)
    if fid is None:
        return "unknown"
    return COARSE_NAMES[FINE_TO_COARSE[fid]]


def build_class_plan(
    records: list[ImageRecord], threshold: int = 200, cap: int = 1500, seed: int = 42
) -> ClassPlan:
    plan = ClassPlan()

    # 1. candidate class per record, resolving aggregates
    candidate: dict[str, str] = {}
    for r in records:
        leaf = r.rel.rsplit("/", 1)[0].rsplit("/", 1)[-1] if "/" in r.rel else r.rel
        if leaf in AGGREGATE_MAP:
            target = AGGREGATE_MAP[leaf]
            if target is None:
                plan.dropped[leaf] = plan.dropped.get(leaf, 0) + 1
                continue
            candidate[r.path] = target
        else:
            candidate[r.path] = leaf

    # 2. fold classes under the threshold into their coarse parent
    counts = Counter(candidate.values())
    remap: dict[str, str] = {}
    for cls, n in counts.items():
        if n >= threshold or cls in COARSE_NAMES:
            continue
        parent = _coarse_parent(cls)
        if parent == "unknown":
            plan.dropped[cls] = n
            continue
        remap[cls] = parent
        plan.folded[cls] = parent

    resolved = {p: remap.get(c, c) for p, c in candidate.items()}
    resolved = {p: c for p, c in resolved.items() if c not in plan.dropped}

    # 3. drop anything still starved after folding
    counts = Counter(resolved.values())
    starved = {c for c, n in counts.items() if n < threshold}
    for c in starved:
        plan.dropped[c] = counts[c]
    resolved = {p: c for p, c in resolved.items() if c not in starved}

    # 4. cap per class, preferring the largest images (stable by path)
    by_class: dict[str, list[ImageRecord]] = defaultdict(list)
    by_path = {r.path: r for r in records}
    for p, c in resolved.items():
        by_class[c].append(by_path[p])

    for cls, items in by_class.items():
        items.sort(key=lambda r: (-(r.width * r.height), r.path))
        for r in items[:cap]:
            plan.assignments[r.path] = cls
        plan.counts[cls] = min(len(items), cap)

    plan.classes = sorted(plan.counts)
    return plan
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_dataset_build.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add backend/ml/dataset_build/restructure.py backend/tests/test_dataset_build.py
git commit -m "feat(dataset): stage 4 classifier restructure, prune and fold"
```

---

## Task 6: Stage 5 — group-aware split

**Files:**
- Create: `backend/ml/dataset_build/split.py`
- Test: `backend/tests/test_dataset_build.py`

**Interfaces:**
- Consumes: `ImageRecord` (Task 2), `ml.grouping` (Task 1)
- Produces:
  - `split_records(records: list[ImageRecord], val_fraction: float = 0.1, seed: int = 42) -> tuple[list[ImageRecord], list[ImageRecord]]`
  - `assert_no_leak(train: list[ImageRecord], val: list[ImageRecord]) -> None` — raises `AssertionError` on any shared group

- [ ] **Step 1: Write the failing test**

```python
import pytest

from ml.dataset_build.index import ImageRecord
from ml.dataset_build.split import assert_no_leak, split_records


def _s(name):
    return ImageRecord(path=f"/d/{name}", source="detector", rel=name, width=64,
                       height=64, size=100, md5=name, dhash=0)


def test_split_is_roughly_val_fraction():
    recs = [_s(f"img_{i}.jpg") for i in range(1000)]
    train, val = split_records(recs, val_fraction=0.1)
    assert 50 < len(val) < 200
    assert len(train) + len(val) == 1000


def test_split_keeps_clip_frames_together():
    recs = [_s(f"MOT17-02_{i:06d}.jpg") for i in range(50)]
    recs += [_s(f"MOT17-09_{i:06d}.jpg") for i in range(50)]
    train, val = split_records(recs, val_fraction=0.5)
    assert_no_leak(train, val)


def test_split_keeps_roboflow_twins_together():
    recs = [_s(f"frame_1_jpg.rf.{i:012x}.jpg") for i in range(20)]
    recs += [_s(f"other_9_jpg.rf.{i:012x}.jpg") for i in range(20)]
    train, val = split_records(recs, val_fraction=0.5)
    assert_no_leak(train, val)


def test_assert_no_leak_detects_a_leak():
    a = [_s("MOT17-02_000001.jpg")]
    b = [_s("MOT17-02_000002.jpg")]     # same clip
    with pytest.raises(AssertionError):
        assert_no_leak(a, b)


def test_split_is_deterministic():
    recs = [_s(f"img_{i}.jpg") for i in range(500)]
    t1, v1 = split_records(recs, seed=42)
    t2, v2 = split_records(list(reversed(recs)), seed=42)
    assert {r.path for r in v1} == {r.path for r in v2}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_dataset_build.py -v -k split`
Expected: FAIL — no module `ml.dataset_build.split`

- [ ] **Step 3: Implement `ml/dataset_build/split.py`**

```python
"""Stage 5 — leak-free, group-aware train/val split.

Orthogonal to Stage 2 dedup and both are required: grouping catches near-
identical frames sharing a filename lineage, dedup catches identical images
saved under unrelated names.
"""

from __future__ import annotations

import os
from collections import defaultdict

from ml.dataset_build.index import ImageRecord
from ml.grouping import family, group_key, stable_bucket


def split_records(
    records: list[ImageRecord], val_fraction: float = 0.1, seed: int = 42
) -> tuple[list[ImageRecord], list[ImageRecord]]:
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
        # a family whose groups all hash high would contribute no val at all
        if keys and not picked:
            picked = {min(keys, key=lambda k: stable_bucket(k, seed))}
        for k in keys:
            (val if k in picked else train).extend(groups[k])

    train.sort(key=lambda r: r.path)
    val.sort(key=lambda r: r.path)
    return train, val


def assert_no_leak(train: list[ImageRecord], val: list[ImageRecord]) -> None:
    tk = {group_key(os.path.basename(r.path)) for r in train}
    vk = {group_key(os.path.basename(r.path)) for r in val}
    shared = tk & vk
    assert not shared, f"LEAK: {len(shared)} group(s) on both sides, e.g. {sorted(shared)[:3]}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_dataset_build.py -v -k split`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/ml/dataset_build/split.py backend/tests/test_dataset_build.py
git commit -m "feat(dataset): stage 5 group-aware leak-free split"
```

---

## Task 7: Stage 6 — emit and verify

**Files:**
- Create: `backend/ml/dataset_build/emit.py`
- Test: `backend/tests/test_dataset_build.py`

**Interfaces:**
- Consumes: everything above
- Produces:
  - `emit_detector(train, val, out_root: Path) -> dict`
  - `emit_classifier(plan: ClassPlan, train, val, out_root: Path) -> dict`
  - `write_dataset_yaml(out_root: Path) -> Path`
  - `verify(out_root: Path) -> list[str]` — returns a list of problems; empty means healthy

Copies are **resumable**: an existing destination file of the same size is
skipped, so a re-run after an interruption continues rather than restarting.

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

from PIL import Image

from ml.dataset_build.emit import emit_detector, verify, write_dataset_yaml
from ml.dataset_build.index import ImageRecord


def _make(tmp_path, name, classes):
    img = tmp_path / "src" / "images" / "train" / name
    img.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (32, 32)).save(img)
    lbl = tmp_path / "src" / "labels" / "train" / Path(name).with_suffix(".txt").name
    lbl.parent.mkdir(parents=True, exist_ok=True)
    lbl.write_text("".join(f"{c} 0.5 0.5 0.1 0.1\n" for c in classes))
    return ImageRecord(path=str(img), source="detector", rel=f"images/train/{name}",
                       width=32, height=32, size=100, md5=name, dhash=0)


def test_emit_detector_copies_images_and_labels(tmp_path):
    tr = [_make(tmp_path, "a.jpg", [0])]
    va = [_make(tmp_path, "b.jpg", [7])]
    out = tmp_path / "dataset"
    stats = emit_detector(tr, va, out)
    assert (out / "detector" / "images" / "train" / "a.jpg").exists()
    assert (out / "detector" / "labels" / "train" / "a.txt").exists()
    assert (out / "detector" / "images" / "val" / "b.jpg").exists()
    assert stats["train"] == 1 and stats["val"] == 1


def test_emit_is_resumable(tmp_path):
    tr = [_make(tmp_path, "a.jpg", [0])]
    out = tmp_path / "dataset"
    emit_detector(tr, [], out)
    stats = emit_detector(tr, [], out)     # second run
    assert stats["skipped"] == 1


def test_write_dataset_yaml_has_13_classes(tmp_path):
    p = write_dataset_yaml(tmp_path)
    text = p.read_text(encoding="utf-8")
    assert "nc: 13" in text
    assert "military_ground_vehicle" in text


def test_verify_flags_missing_label(tmp_path):
    tr = [_make(tmp_path, "a.jpg", [0])]
    out = tmp_path / "dataset"
    emit_detector(tr, [], out)
    (out / "detector" / "labels" / "train" / "a.txt").unlink()
    problems = verify(out)
    assert any("label" in p for p in problems)


def test_verify_flags_out_of_range_class(tmp_path):
    tr = [_make(tmp_path, "a.jpg", [99])]
    out = tmp_path / "dataset"
    emit_detector(tr, [], out)
    problems = verify(out)
    assert any("class id" in p for p in problems)


def test_verify_clean_dataset_returns_no_problems(tmp_path):
    tr = [_make(tmp_path, "a.jpg", [0])]
    va = [_make(tmp_path, "b.jpg", [7])]
    out = tmp_path / "dataset"
    emit_detector(tr, va, out)
    write_dataset_yaml(out)
    assert verify(out) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_dataset_build.py -v -k "emit or verify or dataset_yaml"`
Expected: FAIL — no module `ml.dataset_build.emit`

- [ ] **Step 3: Implement `ml/dataset_build/emit.py`**

```python
"""Stage 6 — write the release dataset and verify its integrity."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from ml.dataset_build.index import ImageRecord, label_path_for
from ml.taxonomy import COARSE_NAMES, NUM_COARSE


def _copy(src: Path, dst: Path) -> bool:
    """Copy unless an identical-size file is already there. Returns True if copied."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst.stat().st_size == src.stat().st_size:
        return False
    shutil.copy2(src, dst)
    return True


def emit_detector(
    train: list[ImageRecord], val: list[ImageRecord], out_root: Path
) -> dict:
    out_root = Path(out_root)
    stats = {"train": 0, "val": 0, "copied": 0, "skipped": 0, "missing_labels": 0}
    for split, recs in (("train", train), ("val", val)):
        for r in recs:
            src = Path(r.path)
            name = src.name
            img_dst = out_root / "detector" / "images" / split / name
            if _copy(src, img_dst):
                stats["copied"] += 1
            else:
                stats["skipped"] += 1
            lbl_src = label_path_for(r.path)
            lbl_dst = out_root / "detector" / "labels" / split / Path(name).with_suffix(".txt").name
            if lbl_src.exists():
                _copy(lbl_src, lbl_dst)
            else:
                lbl_dst.parent.mkdir(parents=True, exist_ok=True)
                lbl_dst.write_text("")      # explicit background image
                stats["missing_labels"] += 1
            stats[split] += 1
    return stats


def emit_classifier(plan, train: list[ImageRecord], val: list[ImageRecord], out_root: Path) -> dict:
    out_root = Path(out_root)
    stats = {"train": 0, "val": 0, "copied": 0, "skipped": 0}
    for split, recs in (("train", train), ("val", val)):
        for r in recs:
            cls = plan.assignments.get(r.path)
            if cls is None:
                continue
            dst = out_root / "classifier" / split / cls / Path(r.path).name
            if _copy(Path(r.path), dst):
                stats["copied"] += 1
            else:
                stats["skipped"] += 1
            stats[split] += 1
    (out_root / "classifier").mkdir(parents=True, exist_ok=True)
    (out_root / "classifier" / "classes.json").write_text(
        json.dumps({"classes": plan.classes, "counts": plan.counts,
                    "folded": plan.folded, "dropped": plan.dropped}, indent=2),
        encoding="utf-8",
    )
    return stats


def write_dataset_yaml(out_root: Path) -> Path:
    out_root = Path(out_root)
    det = (out_root / "detector").resolve()
    det.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Generated by scripts/build_dataset.py — do not edit by hand.",
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


def verify(out_root: Path) -> list[str]:
    out_root = Path(out_root)
    problems: list[str] = []
    det = out_root / "detector"
    seen: dict[str, str] = {}
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
                if parts and not (0 <= int(parts[0]) < NUM_COARSE):
                    problems.append(f"class id {parts[0]} out of range in {split}/{lbl.name}")
            if img.name in seen and seen[img.name] != split:
                problems.append(f"{img.name} present in both train and val")
            seen[img.name] = split
    return problems
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_dataset_build.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add backend/ml/dataset_build/emit.py backend/tests/test_dataset_build.py
git commit -m "feat(dataset): stage 6 emit + integrity verification"
```

---

## Task 8: CLI orchestrator with stage resume

**Files:**
- Create: `backend/scripts/build_dataset.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: all six stage modules
- Produces: `backend/data/dataset/` plus `manifest.json`, `README.md`, and `.build/` markers

Stage markers live in `data/dataset/.build/<stage>.done`. A re-run skips any
stage whose marker exists; `--force <stage>` deletes that marker and everything
after it.

- [ ] **Step 1: Write the failing test**

```python
import subprocess
import sys
from pathlib import Path


def test_build_dataset_help_runs():
    r = subprocess.run([sys.executable, "scripts/build_dataset.py", "--help"],
                       capture_output=True, text=True, cwd="." )
    assert r.returncode == 0
    assert "--target-detector" in r.stdout
    assert "--threshold" in r.stdout
    assert "--force" in r.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_dataset_build.py -v -k build_dataset_help`
Expected: FAIL — file does not exist

- [ ] **Step 3: Implement `scripts/build_dataset.py`**

```python
"""build_dataset.py — rebuild backend/data into a clean data/dataset/.

Six resumable stages. Re-running skips completed stages; --force <stage>
re-runs that stage and everything after it.

  1 index       scan sources, md5 + dhash
  2 dedup       exact + near duplicate removal (BEFORE any split)
  3 rebalance   choose ~50k detector images, rare classes kept whole
  4 restructure classifier class plan: aggregates, prune, fold, cap
  5 split       group-aware leak-free train/val
  6 emit        copy files, write configs, verify

Non-destructive: never modifies or deletes anything under data/detector_yolo,
data/unified_yolo or data/cropped_classes. Use scripts/cleanup_data.py for that,
and only after training succeeds.

Usage:
  python scripts/build_dataset.py
  python scripts/build_dataset.py --target-detector 40000
  python scripts/build_dataset.py --force rebalance
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ml.dataset_build import dedup as dedup_mod
from ml.dataset_build import emit as emit_mod
from ml.dataset_build import rebalance as rebal_mod
from ml.dataset_build import restructure as restruct_mod
from ml.dataset_build import split as split_mod
from ml.dataset_build.index import read_index, read_label_classes, scan_tree, write_index

STAGES = ["index", "dedup", "rebalance", "restructure", "split", "emit"]
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "dataset"
BUILD = OUT / ".build"


def done(stage: str) -> bool:
    return (BUILD / f"{stage}.done").exists()


def mark(stage: str) -> None:
    BUILD.mkdir(parents=True, exist_ok=True)
    (BUILD / f"{stage}.done").write_text(time.strftime("%Y-%m-%d %H:%M:%S"))


def clear_from(stage: str) -> None:
    for s in STAGES[STAGES.index(stage):]:
        (BUILD / f"{s}.done").unlink(missing_ok=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Rebuild backend/data into data/dataset/")
    ap.add_argument("--target-detector", type=int, default=50000)
    ap.add_argument("--threshold", type=int, default=200, help="min unique images per fine class")
    ap.add_argument("--cap", type=int, default=1500, help="max images per class")
    ap.add_argument("--background-frac", type=float, default=0.05)
    ap.add_argument("--val-fraction", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--force", choices=STAGES, help="re-run this stage and all after it")
    args = ap.parse_args()

    if args.force:
        clear_from(args.force)
    BUILD.mkdir(parents=True, exist_ok=True)
    manifest: dict = {}
    mpath = OUT / "manifest.json"
    if mpath.exists():
        manifest = json.loads(mpath.read_text(encoding="utf-8"))

    def save() -> None:
        mpath.parent.mkdir(parents=True, exist_ok=True)
        mpath.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # ---- 1. index ----
    det_idx, crop_idx = BUILD / "index_detector.jsonl", BUILD / "index_crops.jsonl"
    if not done("index"):
        t = time.time()
        n1 = write_index(scan_tree(DATA / "detector_yolo", "detector"), det_idx)
        print(f"  indexed {n1:,} detector images")
        n2 = write_index(scan_tree(DATA / "cropped_classes", "crops"), crop_idx)
        print(f"  indexed {n2:,} crops")
        manifest["index"] = {"detector": n1, "crops": n2, "seconds": round(time.time() - t)}
        save(); mark("index")
    print("[1/6] index      OK")

    det = read_index(det_idx)
    crops = read_index(crop_idx)

    # ---- 2. dedup ----
    dd, dc = BUILD / "dedup_detector.jsonl", BUILD / "dedup_crops.jsonl"
    if not done("dedup"):
        det_k, det_r = dedup_mod.dedup(det)
        crop_k, crop_r = dedup_mod.dedup(crops)
        write_index(det_k, dd)
        write_index(crop_k, dc)
        (BUILD / "duplicates.jsonl").write_text(
            "\n".join(json.dumps({"dropped": a, "kept": b, "reason": c})
                      for a, b, c in det_r + crop_r), encoding="utf-8")
        manifest["dedup"] = {
            "detector_kept": len(det_k), "detector_removed": len(det_r),
            "crops_kept": len(crop_k), "crops_removed": len(crop_r),
        }
        print(f"  detector {len(det)::,} -> {len(det_k):,}   crops {len(crops):,} -> {len(crop_k):,}")
        save(); mark("dedup")
    print("[2/6] dedup      OK")

    det = read_index(dd)
    crops = read_index(dc)

    # ---- 3. rebalance ----
    sel_path = BUILD / "detector_selected.jsonl"
    if not done("rebalance"):
        labels = {r.path: read_label_classes(r.path) for r in det}
        sel, stats = rebal_mod.select_detector_images(
            det, labels, target=args.target_detector,
            background_frac=args.background_frac, seed=args.seed)
        write_index(sel, sel_path)
        manifest["rebalance"] = stats
        print(f"  selected {len(sel):,} detector images")
        save(); mark("rebalance")
    print("[3/6] rebalance  OK")
    sel = read_index(sel_path)

    # ---- 4. restructure ----
    plan_path = BUILD / "class_plan.json"
    if not done("restructure"):
        plan = restruct_mod.build_class_plan(
            crops, threshold=args.threshold, cap=args.cap, seed=args.seed)
        plan_path.write_text(json.dumps({
            "assignments": plan.assignments, "classes": plan.classes,
            "folded": plan.folded, "dropped": plan.dropped, "counts": plan.counts,
        }), encoding="utf-8")
        manifest["restructure"] = {
            "classes": plan.classes, "counts": plan.counts,
            "folded": plan.folded, "dropped": plan.dropped,
        }
        print(f"  {len(plan.classes)} classes, {len(plan.folded)} folded, "
              f"{len(plan.dropped)} dropped")
        save(); mark("restructure")
    print("[4/6] restructure OK")

    raw = json.loads(plan_path.read_text(encoding="utf-8"))
    plan = restruct_mod.ClassPlan(**raw)

    # ---- 5. split ----
    if not done("split"):
        d_tr, d_va = split_mod.split_records(sel, args.val_fraction, args.seed)
        split_mod.assert_no_leak(d_tr, d_va)
        c_recs = [r for r in crops if r.path in plan.assignments]
        c_tr, c_va = split_mod.split_records(c_recs, args.val_fraction, args.seed)
        split_mod.assert_no_leak(c_tr, c_va)
        for name, recs in (("det_train", d_tr), ("det_val", d_va),
                           ("cls_train", c_tr), ("cls_val", c_va)):
            write_index(recs, BUILD / f"{name}.jsonl")
        manifest["split"] = {"det_train": len(d_tr), "det_val": len(d_va),
                             "cls_train": len(c_tr), "cls_val": len(c_va)}
        print(f"  detector {len(d_tr):,}/{len(d_va):,}   classifier {len(c_tr):,}/{len(c_va):,}")
        save(); mark("split")
    print("[5/6] split      OK")

    d_tr = read_index(BUILD / "det_train.jsonl")
    d_va = read_index(BUILD / "det_val.jsonl")
    c_tr = read_index(BUILD / "cls_train.jsonl")
    c_va = read_index(BUILD / "cls_val.jsonl")

    # ---- 6. emit ----
    if not done("emit"):
        print("  copying detector images (this is the slow part)...")
        ds = emit_mod.emit_detector(d_tr, d_va, OUT)
        print("  copying classifier crops...")
        cs = emit_mod.emit_classifier(plan, c_tr, c_va, OUT)
        emit_mod.write_dataset_yaml(OUT)
        problems = emit_mod.verify(OUT)
        if problems:
            for p in problems[:20]:
                print("  PROBLEM:", p)
            raise SystemExit(f"verification failed with {len(problems)} problem(s)")
        manifest["emit"] = {"detector": ds, "classifier": cs}
        (OUT / "classes.json").write_text(json.dumps({
            "coarse": __import__("ml.taxonomy", fromlist=["x"]).COARSE_NAMES,
            "fine": plan.classes}, indent=2), encoding="utf-8")
        save(); mark("emit")
    print("[6/6] emit       OK")

    print(f"\nDataset ready at {OUT}")
    print(f"  detector yaml : {OUT / 'detector' / 'dataset.yaml'}")
    print(f"  manifest      : {mpath}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Fix the f-string typo and run the test**

There is a deliberate typo above: `{len(det)::,}` has a double colon. Correct it
to `{len(det):,}` before running.

Run: `cd backend && python -m pytest tests/test_dataset_build.py -v -k build_dataset_help`
Expected: PASS

- [ ] **Step 5: Ignore the built dataset in git**

Append to the repo `.gitignore`:

```
backend/data/dataset/
```

- [ ] **Step 6: Run the full build**

Run: `cd backend && python scripts/build_dataset.py`
Expected: six `OK` lines. Stage 1 takes ~20–40 min (hashing 677k images); stage 6
takes ~15–30 min (copying ~75k files). Interrupt and re-run to confirm resume:
completed stages should print `OK` immediately.

- [ ] **Step 7: Sanity-check the output**

```bash
cd backend && python -c "
import json
m=json.load(open('data/dataset/manifest.json'))
print('dedup     ', m['dedup'])
print('selected  ', m['rebalance']['n_selected'])
print('classes   ', len(m['restructure']['classes']))
print('split     ', m['split'])
print(m['restructure']['classes'])
"
```
Expected: ~31 classes; `Two_Wheeler` present in `dropped`, not in `classes`.

- [ ] **Step 8: Commit**

```bash
git add backend/scripts/build_dataset.py .gitignore
git commit -m "feat(dataset): resumable six-stage build_dataset CLI"
```

---

## Task 9: Detector training defaults + benchmark + crash-restart

**Files:**
- Modify: `backend/scripts/train_yolo.py`
- Create: `backend/scripts/run_training.ps1`

**Interfaces:**
- Consumes: `data/dataset/detector/dataset.yaml` (Task 8)
- Produces: `outputs/training/ibvap_coarse/weights/{last,best}.pt`

- [ ] **Step 1: Change the defaults**

In `backend/scripts/train_yolo.py`, edit the argparse block:

```python
DEFAULT_DATA = "data/dataset/detector/dataset.yaml"
...
p.add_argument("--imgsz", type=int, default=640)
p.add_argument("--batch", type=int, default=8,
               help="explicit batch; do NOT use -1 on 6GB (autobatch can OOM mid-run)")
p.add_argument("--model", default="models/ibvap_coarse.pt",
               help="warm-start checkpoint, or a pretrained name like yolo11s.pt")
p.add_argument("--epochs", type=int, default=60)
p.add_argument("--benchmark", action="store_true",
               help="train exactly 1 epoch and report minutes/epoch, then exit")
```

- [ ] **Step 2: Add benchmark handling**

Inside `train()`, immediately before `model.train(...)`:

```python
    if args.benchmark:
        import time
        args.epochs = 1
        t0 = time.time()
```

and immediately after the `model.train(...)` call:

```python
    if args.benchmark:
        mins = (time.time() - t0) / 60
        print(f"\n=== BENCHMARK: {mins:.1f} min/epoch ===")
        for budget in (20, 24):
            print(f"  {budget}h budget -> {int(budget * 60 / mins)} epochs")
        return
```

- [ ] **Step 3: Run the benchmark**

Run: `cd backend && python scripts/train_yolo.py --benchmark`
Expected: one epoch completes and prints a minutes/epoch figure.

**Record the number.** Choose `--epochs` from it:

| min/epoch | epochs in 20 h |
|---:|---:|
| 20 | 60 |
| 25 | 48 |
| 30 | 40 |
| 35 | 34 |
| 40 | 30 |

If it exceeds 40 min/epoch, the fallback ladder is: re-run
`build_dataset.py --force rebalance --target-detector 40000`, then if still
short, `--imgsz 576`. Give up resolution last.

If you hit `RuntimeError: Couldn't open shared file mapping ... 1455`, add
`--workers 0` (already documented in the script's docstring).

- [ ] **Step 4: Create the crash-restart wrapper**

```powershell
# backend/scripts/run_training.ps1
# Restarts training automatically after a transient CUDA/driver fault so an
# overnight run is not lost. Resumes from last.pt, which ultralytics writes
# every epoch.
param(
    [int]$Epochs = 60,
    [int]$MaxRetries = 20
)
$ErrorActionPreference = "Continue"
$last = "outputs/training/ibvap_coarse/weights/last.pt"

for ($i = 1; $i -le $MaxRetries; $i++) {
    if (Test-Path $last) {
        Write-Host "=== attempt $i : resuming from $last ==="
        python scripts/train_yolo.py --resume --model $last
    } else {
        Write-Host "=== attempt $i : fresh start ==="
        python scripts/train_yolo.py --epochs $Epochs
    }
    if ($LASTEXITCODE -eq 0) {
        Write-Host "=== training finished cleanly ==="
        exit 0
    }
    Write-Host "=== exited with $LASTEXITCODE, retrying in 30s ==="
    Start-Sleep -Seconds 30
}
Write-Host "=== gave up after $MaxRetries attempts ==="
exit 1
```

- [ ] **Step 5: Verify resume works**

Start training, let one epoch finish, press Ctrl+C, then run:

Run: `cd backend && python scripts/train_yolo.py --resume --model outputs/training/ibvap_coarse/weights/last.pt`
Expected: resumes at the next epoch, not epoch 1.

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/train_yolo.py backend/scripts/run_training.ps1
git commit -m "feat(train): 640/batch8 defaults, benchmark mode, crash-restart wrapper"
```

---

## Task 10: Classifier rewrite with full resume

**Files:**
- Modify: `backend/scripts/train_classifier.py` (full rewrite)

**Interfaces:**
- Consumes: `data/dataset/classifier/{train,val}/<Class>/` (Task 8)
- Produces: `models/classifier/ibvap_fine.pt`, `models/classifier/classes.json`

The existing `prepare_dataset()` is deleted entirely — its flattening, capping
and splitting now live in `build_dataset.py`, which is what removes the need for
the hardcoded `Military_Aircraft`/`Animal`/`Two_Wheeler` skip-list.

- [ ] **Step 1: Write the failing test**

```python
import subprocess
import sys


def test_train_classifier_help_runs():
    r = subprocess.run([sys.executable, "scripts/train_classifier.py", "--help"],
                       capture_output=True, text=True, cwd=".")
    assert r.returncode == 0
    assert "--arch" in r.stdout
    assert "--resume" in r.stdout


def test_train_classifier_has_no_hardcoded_skiplist():
    src = open("scripts/train_classifier.py", encoding="utf-8").read()
    assert "Military_Aircraft" not in src, "structure fix should remove the skip-list"
    assert "prepare_dataset" not in src, "dataset prep belongs in build_dataset.py"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_dataset_build.py -v -k train_classifier`
Expected: FAIL — the skip-list is still present

- [ ] **Step 3: Rewrite `scripts/train_classifier.py`**

```python
"""train_classifier.py — stage 2 fine-grained classifier (IBVAP).

Reads the prepared ImageFolder tree at data/dataset/classifier/, which
build_dataset.py has already deduplicated, pruned, folded and capped. This
script does no dataset surgery of its own.

Fully resumable: model, optimizer, scheduler and epoch are saved every epoch.

Usage:
  python scripts/train_classifier.py
  python scripts/train_classifier.py --arch resnet50
  python scripts/train_classifier.py --resume
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import timm
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, WeightedRandomSampler
from torchvision import datasets, transforms
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "dataset" / "classifier"
OUT = ROOT / "models" / "classifier"
MEAN, STD = (0.485, 0.456, 0.406), (0.229, 0.224, 0.225)


def loaders(size: int, batch: int, workers: int):
    train_tf = transforms.Compose([
        transforms.RandomResizedCrop(size, scale=(0.6, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(0.3, 0.3, 0.3, 0.05),
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
        transforms.RandomErasing(p=0.25),
    ])
    val_tf = transforms.Compose([
        transforms.Resize(int(size * 1.14)),
        transforms.CenterCrop(size),
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
    ])
    tr = datasets.ImageFolder(DATA / "train", train_tf)
    va = datasets.ImageFolder(DATA / "val", val_tf)

    # class-balanced sampling: the source is still skewed after capping
    counts = [0] * len(tr.classes)
    for _, y in tr.samples:
        counts[y] += 1
    weights = [1.0 / counts[y] for _, y in tr.samples]
    sampler = WeightedRandomSampler(weights, len(weights), replacement=True)

    return (
        DataLoader(tr, batch_size=batch, sampler=sampler, num_workers=workers,
                   pin_memory=True, drop_last=True),
        DataLoader(va, batch_size=batch, shuffle=False, num_workers=workers,
                   pin_memory=True),
        tr.classes,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Train the IBVAP fine-grained classifier")
    ap.add_argument("--arch", default="tf_efficientnetv2_s.in21k_ft_in1k")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--imgsz", type=int, default=224)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    tr, va, classes = loaders(args.imgsz, args.batch, args.workers)
    print(f"{len(classes)} classes | train {len(tr.dataset):,} | val {len(va.dataset):,} | {dev}")

    model = timm.create_model(args.arch, pretrained=True, num_classes=len(classes)).to(dev)
    crit = nn.CrossEntropyLoss(label_smoothing=0.1)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.05)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    scaler = torch.amp.GradScaler(dev)

    OUT.mkdir(parents=True, exist_ok=True)
    ckpt_path = OUT / "last.pt"
    start, best = 0, 0.0
    if args.resume and ckpt_path.exists():
        # weights_only=True: the checkpoint holds only tensors, str, int and
        # float, so there is no reason to allow arbitrary unpickling here.
        ck = torch.load(ckpt_path, map_location=dev, weights_only=True)
        model.load_state_dict(ck["model"])
        opt.load_state_dict(ck["opt"])
        sched.load_state_dict(ck["sched"])
        scaler.load_state_dict(ck["scaler"])
        start, best = ck["epoch"] + 1, ck["best"]
        print(f"resumed from epoch {start}, best acc {best:.4f}")

    for ep in range(start, args.epochs):
        model.train()
        for x, y in tqdm(tr, desc=f"epoch {ep + 1}/{args.epochs}"):
            x, y = x.to(dev, non_blocking=True), y.to(dev, non_blocking=True)
            opt.zero_grad(set_to_none=True)
            with torch.amp.autocast(dev):
                loss = crit(model(x), y)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
        sched.step()

        model.eval()
        correct = total = 0
        with torch.no_grad():
            for x, y in va:
                x, y = x.to(dev), y.to(dev)
                with torch.amp.autocast(dev):
                    pred = model(x).argmax(1)
                correct += (pred == y).sum().item()
                total += y.numel()
        acc = correct / max(total, 1)
        print(f"  epoch {ep + 1}: val acc {acc:.4f}")

        torch.save({"model": model.state_dict(), "opt": opt.state_dict(),
                    "sched": sched.state_dict(), "scaler": scaler.state_dict(),
                    "epoch": ep, "best": max(best, acc), "classes": classes,
                    "arch": args.arch}, ckpt_path)
        if acc > best:
            best = acc
            torch.save({"model": model.state_dict(), "classes": classes,
                        "arch": args.arch, "acc": acc}, OUT / "ibvap_fine.pt")
            (OUT / "classes.json").write_text(json.dumps(classes, indent=2), encoding="utf-8")
            print(f"  new best: {acc:.4f}")

    print(f"\nDone. best val acc {best:.4f}  ->  {OUT / 'ibvap_fine.pt'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_dataset_build.py -v -k train_classifier`
Expected: 2 passed

- [ ] **Step 5: Smoke-test two epochs**

Run: `cd backend && python scripts/train_classifier.py --epochs 2`
Expected: prints class count, trains 2 epochs, writes `models/classifier/last.pt`.

- [ ] **Step 6: Verify resume restores epoch and optimizer**

Run: `cd backend && python scripts/train_classifier.py --epochs 4 --resume`
Expected: prints `resumed from epoch 2, best acc ...` and runs epochs 3–4 only.

- [ ] **Step 7: Commit**

```bash
git add backend/scripts/train_classifier.py backend/tests/test_dataset_build.py
git commit -m "feat(train): rewrite classifier for prepared dataset + full resume"
```

---

## Task 11: Cleanup script

**Files:**
- Create: `backend/scripts/cleanup_data.py`

Reports reclaimable space and deletes only what the operator explicitly
confirms. Refuses to run unless `data/dataset/manifest.json` shows a completed
emit stage.

**Interfaces:**
- Consumes: `data/dataset/manifest.json`
- Produces: console report; deletion only under `--delete`

- [ ] **Step 1: Implement `scripts/cleanup_data.py`**

```python
"""cleanup_data.py — report and optionally reclaim source data space.

Run ONLY after training has succeeded. Defaults to a dry-run report.

Verdicts:
  safe    — reconstructible or empty; deleting costs nothing
  verify  — likely redundant, but confirm the overlap first
  keep    — sole copy of source imagery; deleting prevents rebuilding

Usage:
  python scripts/cleanup_data.py                 # report only
  python scripts/cleanup_data.py --delete safe   # remove the 'safe' entries
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

TARGETS = [
    ("ibvap_coarse_dataset.tar", "safe",
     "Colab packing artifact; rebuildable from detector_yolo."),
    ("colab_pack", "safe", "Empty."),
    ("custom", "safe", "Empty."),
    ("plates", "safe", "Empty."),
    ("unified_yolo", "verify",
     "Older parallel copy of the detector set; confirm it is a subset first."),
    ("cropped_classes", "keep",
     "Sole copy of the ~500k crops not selected; needed to re-tune threshold/cap."),
    ("detector_yolo", "keep",
     "Sole copy of source imagery; dataset/ holds only the curated subset."),
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
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}PB"


def main() -> None:
    ap = argparse.ArgumentParser(description="Report/reclaim source data space")
    ap.add_argument("--delete", choices=["safe", "verify"],
                    help="actually delete entries with this verdict")
    args = ap.parse_args()

    manifest = DATA / "dataset" / "manifest.json"
    if not manifest.exists() or "emit" not in json.loads(manifest.read_text()):
        raise SystemExit("refusing: data/dataset/manifest.json shows no completed emit stage")

    print(f"{'target':<28} {'size':>10}  verdict  reason")
    print("-" * 100)
    reclaim = 0
    for name, verdict, reason in TARGETS:
        p = DATA / name
        if not p.exists():
            continue
        s = size_of(p)
        print(f"{name:<28} {human(s):>10}  {verdict:<7}  {reason}")
        if args.delete and verdict == args.delete:
            reclaim += s

    if not args.delete:
        print("\nDry run. Re-run with --delete safe to reclaim the 'safe' entries.")
        return

    print(f"\nAbout to delete every '{args.delete}' entry, reclaiming {human(reclaim)}.")
    if input("Type DELETE to confirm: ").strip() != "DELETE":
        raise SystemExit("aborted")
    for name, verdict, _ in TARGETS:
        p = DATA / name
        if p.exists() and verdict == args.delete:
            print(f"  removing {name} ...")
            p.unlink() if p.is_file() else shutil.rmtree(p, ignore_errors=True)
    print(f"Reclaimed ~{human(reclaim)}.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it refuses before a build exists**

Run: `cd backend && python scripts/cleanup_data.py`
Expected (before a successful build): `refusing: ... no completed emit stage`.
After a successful build: the report table, ending in the dry-run notice.

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/cleanup_data.py
git commit -m "feat(data): opt-in cleanup script with dry-run default"
```

---

## Task 12: Runbook

**Files:**
- Create: `docs/RUNBOOK_LOCAL_TRAINING.md`

- [ ] **Step 1: Write the runbook**

````markdown
# Runbook — training IBVAP locally on an RTX 4050

Every command runs from `backend/`. All long steps are resumable: re-run the
same command after an interruption.

## 0. Once

```powershell
cd "F:\Projects\SIH 26187\backend"
pip install -r requirements-training.txt
python -c "import torch, timm; print(torch.cuda.get_device_name(0), timm.__version__)"
```

Disable sleep for the run:
```powershell
powercfg /change standby-timeout-ac 0
powercfg /change monitor-timeout-ac 15
```

## 1. Build the dataset (~1–2 h, resumable)

```powershell
python scripts/build_dataset.py
```

Interrupted? Re-run the same command — completed stages print `OK` instantly.
Re-run one stage with e.g. `--force rebalance`.

Check the result:
```powershell
python -c "import json;m=json.load(open('data/dataset/manifest.json'));print(m['split']);print(len(m['restructure']['classes']),'classes')"
```

## 2. Benchmark one epoch (~30 min)

```powershell
python scripts/train_yolo.py --benchmark
```

Read the `min/epoch` figure and pick `--epochs`:

| min/epoch | epochs in 20 h |
|---:|---:|
| 20 | 60 |
| 25 | 48 |
| 30 | 40 |
| 35 | 34 |
| 40 | 30 |

Above 40 min/epoch:
```powershell
python scripts/build_dataset.py --force rebalance --target-detector 40000
# still short? then, and only then:
python scripts/train_yolo.py --benchmark --imgsz 576
```

## 3. Train the detector (~20 h, resumable)

```powershell
.\scripts\run_training.ps1 -Epochs 48
```

The wrapper restarts automatically on a crash and resumes from `last.pt`.
To resume by hand after closing the terminal:

```powershell
python scripts/train_yolo.py --resume --model outputs/training/ibvap_coarse/weights/last.pt
```

Watch progress:
```powershell
Get-Content outputs/training/ibvap_coarse/results.csv -Tail 5
```

## 4. Train the classifier (~1.5 h, resumable)

```powershell
python scripts/train_classifier.py --epochs 30
python scripts/train_classifier.py --epochs 30 --resume   # after an interruption
```

## 5. Evaluate

```powershell
python -m ml.eval_detector --weights outputs/training/ibvap_coarse/weights/best.pt
```

Compare per-class mAP against the Colab baseline (mAP50 0.63 at epoch 9), paying
attention to `military_ground_vehicle`, `bus` and `helicopter`.

## 6. Install the weights

```powershell
Copy-Item outputs/training/ibvap_coarse/weights/best.pt models/ibvap_coarse.pt
```

## 7. Reclaim disk (only after 5 looks good)

```powershell
python scripts/cleanup_data.py                # report
python scripts/cleanup_data.py --delete safe  # ~34 GB, tar + empty dirs
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Couldn't open shared file mapping ... 1455` | Add `--workers 0`, or raise the Windows page file to 32 GB |
| `CUDA out of memory` | Lower `--batch` to 6 or 4; never use `--batch -1` |
| Training restarts at epoch 1 | You passed `--epochs` instead of `--resume`; resume needs `--resume --model .../last.pt` |
| `build_dataset.py` re-runs a finished stage | A `--force` flag cleared its marker; markers live in `data/dataset/.build/` |
| Disk full during emit | Emit is resumable — free space and re-run the same command |
````

- [ ] **Step 2: Commit**

```bash
git add docs/RUNBOOK_LOCAL_TRAINING.md
git commit -m "docs: runbook for local RTX 4050 training"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §5 Stage 1 index | Task 2 |
| §5 Stage 2 dedup | Task 3 |
| §5 Stage 3 rebalance | Task 4 |
| §5 Stage 4 restructure/prune/fold | Task 5 |
| §5 Stage 5 split (reuses make_clean_split) | Tasks 1, 6 |
| §5 Stage 6 emit + verify | Task 7 |
| §5 stage markers / resume | Task 8 |
| §6 detector training, 640/batch 8, benchmark, crash-restart | Task 9 |
| §7 classifier rewrite, full resume | Task 10 |
| §8 disposal | Task 11 |
| §9 testing | Tasks 1–7, 10 |
| §11 runbook | Task 12 |

All covered.

**Known deviations from the spec, deliberate:**
- Spec §5 describes one `build_dataset.py`. The plan splits the stages into
  `ml/dataset_build/*` modules with a thin CLI, because six stages in one file
  would be unwieldy and untestable. The CLI surface is unchanged.
- Spec §4 shows `README.md` inside `data/dataset/`. The plan writes the
  human-facing documentation to `docs/RUNBOOK_LOCAL_TRAINING.md` instead, since
  `data/dataset/` is gitignored and a README there would not be version
  controlled. `manifest.json` and `classes.json` are still emitted.
- Spec §7 estimated ~25k crops; the actual number is whatever the cap and
  threshold produce, recorded in the manifest.
