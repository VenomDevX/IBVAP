# Runbook — training IBVAP locally on an RTX 4050

Everything runs from `backend/`, using the project venv. **Use
`.\venv\Scripts\python.exe`, not bare `python`** — the system Python has neither
pytest nor torch.

```powershell
cd "F:\Projects\SIH 26187\backend"
```

Every long step is resumable: after an interruption, re-run the same command.

---

## 0. Once per machine

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-training.txt
.\venv\Scripts\python.exe -c "import torch, timm; print(torch.cuda.get_device_name(0), torch.__version__, timm.__version__)"
```

Expected: `NVIDIA GeForce RTX 4050 Laptop GPU 2.5.1+cu121 1.0.29`

Stop the laptop sleeping mid-run:

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change monitor-timeout-ac 15
```

---

## 1. Build the dataset  (~50–70 min, resumable)

```powershell
.\venv\Scripts\python.exe scripts/build_dataset.py
```

Six stages, each writing a marker under `data/dataset/.build/`. Interrupted?
Re-run the same command — finished stages print `OK` instantly.

| stage | what it does | time |
|---|---|---|
| 1 index | hash every source image (md5 + dHash), 8 worker processes | ~17 min |
| 2 dedup | exact + near duplicates, **before** any split | ~12 min |
| 3 rebalance | pick ~50k detector images, keeping every rare-class frame | ~2 min |
| 4 restructure | resolve aggregates, prune, fold, cap | ~1 min |
| 5 split | group-aware leak-free train/val | ~1 min |
| 6 emit | copy files, write configs, verify | ~20–40 min |

Useful variants:

```powershell
# see the class plan without the 20-40 min copy
.\venv\Scripts\python.exe scripts/build_dataset.py --dry-run

# re-run one stage and everything after it
.\venv\Scripts\python.exe scripts/build_dataset.py --force rebalance

# smaller detector set if the benchmark in step 2 comes back slow
.\venv\Scripts\python.exe scripts/build_dataset.py --force rebalance --target-detector 40000
```

Check the result:

```powershell
.\venv\Scripts\python.exe -c "import json; m=json.load(open('data/dataset/manifest.json')); print(m['split']); print(len(m['restructure']['classes']), 'classes'); print(m['dedup'])"
```

**The build is non-destructive.** It never touches `data/detector_yolo`,
`data/unified_yolo` or `data/cropped_classes`.

---

## 2. Benchmark one epoch  (~30 min)

Do not skip this. It replaces a guess with a measurement from your actual GPU.

```powershell
.\venv\Scripts\python.exe scripts/train_yolo.py --benchmark
```

It prints `min/epoch` and the epoch counts that fit 12/20/24 hours. Pick
`--epochs` from that table.

If it reports over 40 min/epoch, the fallback ladder — **give up resolution
last**, it costs the most accuracy on the distant objects this system exists to
spot:

```powershell
# 1. smaller detector set
.\venv\Scripts\python.exe scripts/build_dataset.py --force rebalance --target-detector 40000
# 2. only if still short
.\venv\Scripts\python.exe scripts/train_yolo.py --benchmark --imgsz 576
```

---

## 3. Train the detector  (~20 h, resumable)

```powershell
.\scripts\run_training.ps1 -Epochs 48
```

The wrapper restarts and resumes from `last.pt` after a transient CUDA fault, so
one hiccup does not cost the night. To resume by hand after closing the terminal:

```powershell
.\venv\Scripts\python.exe scripts/train_yolo.py --resume --model outputs/training/ibvap_coarse/weights/last.pt
```

Watch progress from another terminal:

```powershell
Get-Content backend/outputs/training/ibvap_coarse/results.csv -Tail 5
```

---

## 4. Train the classifier  (~1–2 h, resumable)

```powershell
.\venv\Scripts\python.exe scripts/train_classifier.py --epochs 30
.\venv\Scripts\python.exe scripts/train_classifier.py --epochs 30 --resume   # after an interruption
```

Resume restores optimizer, scheduler and AMP scaler state — not just weights —
so the cosine LR schedule continues from the right place.

It selects the best epoch on **macro-recall, not accuracy**. Accuracy is
dominated by Person and Car; a model that ignored every military type entirely
would still post a flattering top-line number.

---

## 5. Evaluate

```powershell
.\venv\Scripts\python.exe -m ml.eval_detector --weights outputs/training/ibvap_coarse/weights/best.pt
```

Compare per-class mAP against the Colab baseline (mAP50 **0.63**, recall
**0.59** at epoch 9). The classes to actually look at are the ones that were
starved before: `military_ground_vehicle` (681 boxes), `bus` (799),
`helicopter` (1,642). Overall mAP50 can move either way; if those three improve,
the rebuild did its job.

---

## 6. Install the weights

```powershell
Copy-Item outputs/training/ibvap_coarse/weights/best.pt models/ibvap_coarse.pt
```

---

## 7. Reclaim disk — only after step 5 looks good

```powershell
.\venv\Scripts\python.exe scripts/cleanup_data.py                # report, deletes nothing
.\venv\Scripts\python.exe scripts/cleanup_data.py --delete safe  # ~34 GB
```

Only the Colab tar and the empty directories are marked `safe`.
`cropped_classes` and `detector_yolo` are deliberately marked **keep**: they are
the sole copy of the source imagery, and deleting them means you can never
re-run the build at a different threshold, cap or target — which is exactly what
you will want after seeing the first results.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Couldn't open shared file mapping ... 1455` | `--workers 0`, or raise the Windows page file to 32 GB |
| `CUDA out of memory` | Lower `--batch` to 6 or 4. **Never `--batch -1`** — autobatch probes VRAM at startup and can OOM hours later |
| Training restarts at epoch 1 | You passed `--epochs` instead of resuming. Use `--resume --model .../last.pt` |
| Build process killed / machine unresponsive | Memory. Close other apps; the build peaks during stage 2. It is resumable — just re-run |
| `build_dataset.py` re-runs a finished stage | A `--force` cleared its marker. Markers live in `data/dataset/.build/` |
| Disk full during emit | Emit is resumable — free space and re-run the same command |
| `ModuleNotFoundError: No module named 'ml'` | You used the system Python. Use `.\venv\Scripts\python.exe` |

---

## What the rebuild actually fixed

Measured on the real corpus, not assumed:

- **71.6%** of detector boxes were `person`; `military_ground_vehicle` sat at
  1:519. Rebalance keeps 100% of rare-class frames and subsamples the person/car
  bulk, which raises rare-class frequency *and* halves epoch time.
- **14.7%** of detector images were empty backgrounds (norm is 1–10%), now
  capped at 5%.
- The aggregate folders were **byte-identical copies** of their children —
  `Two_Wheeler` = Bicycle + Motorcycle exactly (6,716 = 4,566 + 2,150), `Animal`
  = Dog+Bird+Cat+Horse+Sheep+Cow exactly (7,994). They inflated the apparent
  corpus size and, resolved naively, destroyed the specific classes.
- **3,090 images are byte-identical under conflicting labels** — every Forklift
  image is also filed as Car, every Bus image is also filed as Car. Those are
  dropped rather than resolved by a coin flip.
- Duplicates are removed **before** the split. Previously
  `train_classifier.py` split after collecting paths, so identical images landed
  on both sides and reported accuracy was partly measuring memorisation.
