# IBVAP — Local Training on RTX 4050: Dataset Rebuild + Two-Stage Training

**Date:** 2026-09-09
**Status:** Approved design, pending implementation
**Scope:** Spec 1 of 2. Covers dataset rebuild and both training stages.
Pipeline wiring (`backend/src/classification/`) is deferred to Spec 2.

---

## 1. Problem

Training moved off Colab (GPU quota exhausted, disconnects lost progress) onto a
local **RTX 4050 Laptop, 6 GB VRAM**. The hard constraint is a **1–1.5 day total
training budget**, and the goal is high accuracy on a two-stage detector +
fine-grained classifier.

The current dataset cannot meet that goal. An audit on 2026-09-09 found:

### 1.1 Detector set — `data/detector_yolo`, 107,438 train / 12,200 val

493,887 train boxes, distributed:

| id | class | boxes | % | images | imbalance |
|---:|---|---:|---:|---:|---|
| 0 | person | 353,464 | 71.57% | 39,111 | 1:1 |
| 11 | night_vision_object | 43,558 | 8.82% | 13,988 | 1:8 |
| 1 | car | 36,667 | 7.42% | 4,906 | 1:10 |
| 8 | aircraft | 20,394 | 4.13% | 15,692 | 1:17 |
| 6 | license_plate | 17,220 | 3.49% | 16,061 | 1:21 |
| 12 | animal | 7,153 | 1.45% | 4,348 | 1:49 |
| 10 | drone_uav | 4,240 | 0.86% | 4,082 | 1:83 |
| 5 | bicycle | 4,151 | 0.84% | 1,805 | 1:85 |
| 3 | truck | 1,973 | 0.40% | 1,720 | 1:179 |
| 4 | motorcycle | 1,945 | 0.39% | 1,602 | 1:182 |
| 9 | helicopter | 1,642 | 0.33% | 1,370 | 1:215 |
| 2 | bus | 799 | 0.16% | 643 | 1:442 |
| 7 | military_ground_vehicle | 681 | 0.14% | 623 | **1:519** |

Plus **15,741 empty images (14.7%)** with no boxes at all. Best practice is
1–10% background.

The Colab run confirmed the consequence: mAP50 plateaued at ~0.63 with recall
0.59 by epoch 9. Person carries the score; the tail drags it down.

### 1.2 Crop set — `data/cropped_classes`, 557,005 images in 91 folders

- `People/Person` 396,181 (71.1%) down to `Military/KJ600` **10 images**.
  **39,618× imbalance.**
- **43 of 91 classes hold under 200 images** (`B21` 20, `An225` 27, `Ka27` 32).
- **14.5% byte-identical duplicates, 17.7% near-duplicates** (sampled 33,478
  images, 8×8 dHash). Concentrated in the military classes: `P3` 20.1%,
  `WZ7` 21.6%, `TB001` 20.4%, `Su57` 18.6%, `AH64` 18.6%, `EF2000` 16.8%.

### 1.3 Structural defects

- **Aggregate folders sit beside their own children and double-count.**
  `Military_Aircraft` (14,447) alongside `Military/F16`…; `Animal` (7,994)
  alongside `Animals/Dog`…; `Two_Wheeler` (6,716) alongside `Vehicles/Bicycle`
  + `Vehicles/Motorcycle`. `scripts/train_classifier.py` carries a hardcoded
  skip-list for exactly these three — a band-aid over a structural bug.
- **Inconsistent naming:** `Animal` vs `Animals`, `Military` vs
  `Military_Aircraft`.
- **Two overlapping detector copies:** `unified_yolo` (101,434 images) and
  `detector_yolo` (119,706). Plus a 34 GB `ibvap_coarse_dataset.tar` built for
  Colab, now unused. `custom/`, `plates/`, `colab_pack/` are empty.
- **Orphans:** `detector_yolo` holds 109,385 train images on disk but only
  107,438 appear in `splits/train_coarse.txt`.

### 1.4 The leak

`train_classifier.py` builds its train/val split *after* collecting file paths,
with no dedup. With 14.5% exact duplicates, identical images appear on both
sides of the split. **Reported classifier val accuracy is inflated** — it is
partly measuring memorization. Any accuracy number produced before this fix is
unreliable.

---

## 2. Key insight

The speed problem and the accuracy problem share one solution.

107k images is too slow for a 6 GB laptop GPU inside a 1.5-day budget. But most
of that volume is redundant person frames. Curating the set makes training
**faster and more accurate simultaneously**: dropping person-only redundancy and
capping backgrounds cuts the set roughly in half (≈2× faster epochs) while
*raising* rare-class mAP, because the rare classes stop being drowned.

Therefore: rebuild the dataset first, then train. Not the other way round.

---

## 3. Goals / Non-goals

**Goals**
- One clean, browsable, physically-organised `backend/data/dataset/` folder.
- Duplicates removed *before* splitting, so no train/val leakage.
- Class imbalance reduced to a trainable range at both stages.
- Both stages train to completion within ~30 h wall-clock on an RTX 4050 6 GB.
- Every long-running step resumable at epoch or stage granularity.
- Deterministic and reproducible: seeded, with a manifest recording every
  decision.

**Non-goals (this spec)**
- Wiring the classifier into the live inference pipeline — that is Spec 2.
- Collecting new imagery. We work with what exists.
- Multi-GPU or distributed training.
- Deleting source data as part of the build (see §8).

---

## 4. Target structure

Physically copied — inspectable, not a set of index files pointing at the old
mess. Estimated footprint **≈17–19 GB** (detector ~14 GB at ~285 KB/image;
classifier crops ~3–5 GB) against **83 GB free**.

```
backend/data/dataset/
├── README.md              generated: what this is, how it was built, how to retrain
├── manifest.json          provenance: every count, dedup stat, cap and prune decision
├── classes.json           both taxonomies in one file
│
├── detector/              STAGE 1 — YOLO, 13 coarse classes
│   ├── dataset.yaml       ultralytics data config, absolute paths
│   ├── images/
│   │   ├── train/
│   │   └── val/
│   └── labels/
│       ├── train/
│       └── val/
│
└── classifier/            STAGE 2 — fine-grained, ~33 classes
    ├── classes.json
    ├── train/
    │   ├── Person/  Car/  Bus/  Tank/  F16/  F35/  C130/  ...
    │   └── aircraft/  helicopter/  drone_uav/     ← catch-alls for folded types
    └── val/
        └── (same class folders)
```

The classifier class list is **derived at build time**, not hardcoded: the 31
fine classes that clear the threshold (§5 Stage 4), plus coarse catch-all
buckets absorbing the folded remainder — `aircraft` (absorbing `Generic_Jet`
and every pruned fixed-wing type), `helicopter` (`AH64`, `Mi24`, …) and
`drone_uav` (`MQ9`, `RQ4`, …). `military_ground_vehicle` is expected to be empty
since `Tank` survives on its own. Expected total ≈ 33. The authoritative list is
written to `classes.json` and `manifest.json` by the build.

Class folder names use the exact strings from `backend/ml/taxonomy.py`
(`FINE_NAMES` for fine classes, `COARSE_NAMES` for coarse). No third naming
scheme is invented; `taxonomy.py` stays the single source of truth.

---

## 5. Component 1 — `scripts/build_dataset.py`

Single idempotent entry point. Six stages, each writing a completion marker to
`data/dataset/.build/` so a re-run skips finished work. `--force <stage>`
re-runs one stage.

### Stage 1 — Index
Walk `detector_yolo` and `cropped_classes` via `os.scandir`. For each file
record path, size, resolution, md5, and 8×8 dHash into
`.build/index.jsonl`. This is the only full pass over the source data;
everything downstream reads the index.

### Stage 2 — Dedup
1. **Exact:** group by md5, keep one representative.
2. **Near:** group by dHash with Hamming distance ≤ 3, keep the
   highest-resolution member.

Runs **before** any split, which is what closes the leak in §1.4. Removed
pairs are logged to `.build/duplicates.jsonl` so the decision is auditable.

### Stage 3 — Rebalance detector
Per image, compute the rarest class present. Then:
- **Keep 100%** of images containing any of `military_ground_vehicle`, `bus`,
  `helicopter`, `truck`, `motorcycle`, `drone_uav`, `animal`, `bicycle`.
- **Subsample** images whose only content is `person` and/or `car`, to a
  configurable ceiling, preferring images with more boxes and higher resolution.
- **Cap empty backgrounds** from 14.7% to **5%** of the final set.

Target ≈ **50,000 images**, tunable via `--target-detector`.

Rare-class images are never dropped, so absolute rare-class box counts are
preserved while their *relative* frequency rises substantially.

### Stage 4 — Restructure classifier
- Resolve the aggregate/child overlap: `Military_Aircraft`, `Animal` and
  `Two_Wheeler` become genuine parents, never siblings of their own children.
  This removes the need for the hardcoded skip-list.
- Canonicalise names through `taxonomy.py`.
- **Prune** any class with fewer than **200 unique** (post-dedup) images; fold
  it into its coarse parent via `FINE_TO_COARSE`. Folding is not discarding: an
  `AH64` crop becomes training data for `helicopter`, so the model still learns
  from it and answers at coarse granularity.
- **Cap** at 1,500 images per class, sampling the highest-resolution members.

**Expected survivors: 31 classes — 14 civilian + 17 military.**

| | classes |
|---|---|
| Civilian (14) | Person, Car, Night_Vision_Object, Bicycle, Forklift, Motorcycle, Bus, Dog, Bird, Cat, Horse, Cow, Sheep, Generic_Jet |
| Military (17) | Tank, F15, F16, F18, F35, A10, B1, C130, C2, EF2000, J10, J20, JAS39, Rafale, Su34, US2, V22 |

#### Why 200 and not 400

The threshold was simulated at both values against real per-class duplicate
rates. **The two settings keep an identical civilian class list** — every
civilian class clears 400 comfortably (the smallest, `Bus`, has ~730 unique).
The threshold therefore only ever bites on military classes:

| | ≥200 | ≥400 |
|---|---:|---:|
| total classes | 31 | 18 |
| military types | **17** | **4** |

At 400 the only military survivors are `F15`, `F16`, `F18`, `Tank`. Lost would
be `F35` (389 unique — missing the cut by 11 images), `C130` (367), `C2` (347),
`A10` (274), `V22` (262), `B1` (242), plus **every helicopter** (`AH64` 125,
`Mi24` 120) and **every drone** (`MQ9` 151, `RQ4` 108). Since `taxonomy.py`
defines stage 2's purpose as fine-grained ID across
aircraft/helicopter/drone_uav/military_ground_vehicle, a 4-class military output
would not justify the stage.

Raising the floor does not make the model more accurate — it makes the task
easier and less useful. The levers for accuracy at a fixed class count are the
per-class cap, augmentation and epoch count, not the prune floor.

### Stage 5 — Split
Group-aware and seeded (`seed=42`, `val_fraction=0.1`), grouping by source image
and MOT/VIRAT clip so frames from one clip never straddle the split.

Reuses `scripts/make_clean_split.py` directly rather than reimplementing —
specifically `group_key()` (strips Roboflow `.rf.<hash>` suffixes and trailing
frame numbers to a clip id), `family()` for per-source stratification, and
`stable_bucket()` for deterministic md5-seeded assignment. That module already
asserts no group lands on both sides; the assertion is kept.

Note this is *orthogonal* to Stage 2 dedup and both are required. Grouping
catches near-identical frames that share a filename lineage; dHash dedup catches
byte- or pixel-identical images that do not (the same aircraft photo saved twice
under different names, which is the dominant pattern in `cropped_classes`).

### Stage 6 — Emit
Copy files into the §4 layout, write `dataset.yaml`, `classes.json`,
`manifest.json`, `README.md`. Verify: every image has a label, no label
references an out-of-range class id, no file appears in both train and val.
Build fails loudly if any check fails.

---

## 6. Component 2 — Stage 1 detector training

`scripts/train_yolo.py` already exists and is tuned for a 6 GB RTX 40-series
(explicit SGD schedule, disk cache, AMP, `CUBLAS_WORKSPACE_CONFIG` workaround,
Windows `--workers` guidance). Changes required:

- Point `--data` at `data/dataset/detector/dataset.yaml`.
- **`--imgsz 640`** — YOLO's native resolution, which the pretrained weights are
  tuned for. At batch 8 with AMP this occupies ~4–4.5 GB, leaving headroom
  inside 6 GB after Windows takes ~0.7 GB for display. 704px (batch 6) and 768px
  (batch 4) were considered and rejected: both risk OOM on a 6 GB laptop card,
  and the reduced batch measurably degrades BatchNorm statistics.
- **`--batch 8` explicitly, never `-1`.** Autobatch probes VRAM at startup and
  can pick a size that OOMs later once activations peak, killing an overnight run.
- Warm-start from `models/ibvap_coarse.pt` rather than `yolo11s.pt`.
- `--workers 2` (Windows-safe; drop to 0 on the `shared file mapping ... 1455`
  page-file error already documented in the script).

**Resume** already works via `--resume`, reading `last.pt`, which ultralytics
writes every epoch. A wrapper script restarts automatically on crash so a
transient CUDA error does not cost the remaining night.

### Epoch budget is measured, not assumed
Step 0 of training is a **1-epoch benchmark** producing a real minutes/epoch
figure on this specific machine. Epoch count is then chosen from a table:

| measured min/epoch | epochs in 20 h |
|---:|---:|
| 20 | 60 |
| 25 | 48 |
| 30 | 40 |
| 35 | 34 |
| 40 | 30 |

My estimate is 22–34 min/epoch at 50k images, 640px, batch 8 — but the estimate
is not load-bearing. The measurement decides.

If the measurement lands above 40 min/epoch, the fallback ladder is, in order:
reduce `--target-detector` to 40k, then drop to `--imgsz 576`. Resolution is
given up last, since it costs the most accuracy on distant objects.

---

## 7. Component 3 — Stage 2 classifier training

Rewrite `scripts/train_classifier.py`:

- **Drop `prepare_dataset()` entirely.** Its flattening, capping and splitting
  all move into `build_dataset.py`; the trainer now simply reads the prepared
  `ImageFolder` tree. This also deletes the hardcoded skip-list.
- **Architecture:** EfficientNetV2-S via `timm` (default), `--arch resnet50`
  retained. `timm>=1.0.0` is already in `requirements-training.txt`.
- 224px, AMP, batch 64 — comfortable inside 6 GB.
- Class-balanced sampling (`WeightedRandomSampler`, already present) plus label
  smoothing 0.1.
- **Full resume:** model + optimizer + scheduler + epoch + RNG state written to
  `last.pt` every epoch; `--resume` restores all of it. The current script saves
  weights only and cannot truly resume.
- Emits `models/classifier/ibvap_fine.pt` and `classes.json`.

Estimated ~25k crops after the 1,500/class cap (≈17k civilian + ≈5.5k military
fine + the catch-all buckets). At 224px/batch 64 that is ~2–3 min/epoch;
30 epochs ≈ 1–1.5 h. Stage 2 is cheap — the detector dominates the budget.

---

## 8. Source data disposal

The build is **strictly non-destructive**. Nothing under `data/detector_yolo`,
`data/unified_yolo`, `data/cropped_classes` or the tar is modified or removed
during the build.

Deletion is a **separate, explicit second step** (`--cleanup`), run only after
the new dataset has trained successfully. Rationale: deleting 557k source crops
before stage 2 has demonstrably converged destroys the ability to re-tune the
prune threshold or per-class cap, and the build cannot be re-run.

The build emits a cleanup report ranking candidates:

| Candidate | Size | Verdict |
|---|---|---|
| `data/ibvap_coarse_dataset.tar` | 34 GB | **Safe.** A Colab packing artifact; Colab is no longer used and it is reconstructible from `detector_yolo`. |
| `data/colab_pack/`, `data/custom/`, `data/plates/` | 0 | **Safe.** Empty. |
| `data/unified_yolo/` | 101,434 images | **Verify first.** Report quantifies overlap with `detector_yolo`; delete only if it proves to be a strict subset. |
| `data/cropped_classes/` | 557,005 images | **Keep** until stage 2 converges. Sole copy of the ~500k crops not selected. |
| `data/detector_yolo/` | 119,706 images | **Keep.** Sole copy of source imagery; `dataset/` holds only the curated ~50k. |

Deleting just the tar and the empty directories reclaims **~34 GB** at zero risk.

---

## 9. Testing

- **`build_dataset.py`:** unit tests on a synthetic fixture tree covering dedup
  (exact + near), the aggregate/child overlap, prune-and-fold, background cap,
  and group-aware split. Assert no file appears in both train and val — the
  regression test for §1.4.
- **Verification pass** inside Stage 6 (see §5) fails the build on any
  integrity violation.
- **Trainers:** 1-epoch smoke runs on a tiny fixture, asserting a checkpoint is
  written and `--resume` restores epoch, optimizer and scheduler state.
- **Detector quality gate:** `python -m ml.eval_detector` on the held-out val
  split; compare per-class mAP against the Colab baseline (mAP50 0.63 @ epoch 9)
  with particular attention to `military_ground_vehicle`, `bus` and `helicopter`.

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| Measured epoch time far exceeds estimate | Benchmark is step 0; epoch count chosen from the §6 table. Fall back to 512px or a smaller `--target-detector`. |
| OOM mid-run on 6 GB | Explicit `batch 8`, never autobatch. Crash-restart wrapper resumes from `last.pt`. |
| Windows `shared file mapping 1455` | `--workers 0` fallback, already documented in `train_yolo.py`. |
| Subsampling person hurts person mAP | Person has 353k boxes; even at 20% retention it keeps ~70k, far above any other class. Verified by the quality gate. |
| Prune threshold leaves too few classes | Threshold is a flag. Manifest records exactly what was pruned, so it is re-runnable at a different value. |
| Laptop thermal throttling extends epochs | Benchmark runs long enough to reach steady-state clocks, so the measurement includes throttling. |

---

## 11. Deliverables

1. `backend/scripts/build_dataset.py` — six-stage resumable builder
2. `backend/scripts/cleanup_data.py` — separate, explicit disposal step
3. `backend/scripts/train_yolo.py` — updated defaults, crash-restart wrapper
4. `backend/scripts/train_classifier.py` — rewritten, fully resumable
5. `backend/tests/test_build_dataset.py` — fixture-based tests
6. `backend/data/dataset/` — the built dataset (gitignored)
7. A runbook of exact terminal commands, in order, with resume instructions

---

## 12. Open questions

None blocking. Epoch counts are resolved by measurement at training step 0.
