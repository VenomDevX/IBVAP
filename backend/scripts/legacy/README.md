# Legacy data-prep scripts — kept for provenance only

These built the **old 91-class** `unified_yolo` dataset. They are **superseded** and
should not be run for the current (coarse) pipeline.

| script | what it did | why retired |
|---|---|---|
| `merge_datasets.py` | first `unified_yolo` builder — MOT17 + a plate set | plate label rewrite silently produced no `.txt` files (the "0 plate labels" bug); wrong class ids for the later taxonomy |
| `merge_military.py` | added military / thermal / night-vision sets under a 6–8 class interim taxonomy | interim ids required a second remap pass; fragile `path.replace("images","labels")` |
| `add_external.py` | 6-class add of Border Defence + People Detection | **conflicts** with `add_granular_external.py` — same file prefixes, incompatible class maps |
| `add_granular_external.py` | 91-class add of the same two sets | assumes the Border Defence export class order maps 1:1 onto ids 18–90; no validation |
| `fix_existing_labels.py` | in-place second remap (virat 1→2, milfield 3→9/6→8, nightvis 7→17, plate 2→7) | brittle chained remapping; only touched `labels/train` |
| `fix_labels_and_split.py` | coord clamping + a **random 10 % file split** | random split = the Roboflow augmentation leak that `make_clean_split.py` was written to fix |
| `download_plates.py` | Roboflow SDK pull of `license-plate-recognition-rxg4e` **v4** | pinned to v4; the current plate data is v13 and merged via `scripts/add_plates.py` |

## Current pipeline (from `backend/`)

```
python -m ml.remap_to_coarse                      # unified_yolo (91-class) -> detector_yolo (13-class)
python scripts/add_plates.py --src "<...v13i.yolov8>" --dst data/detector_yolo --purge-old --limit 18000
python scripts/make_clean_split.py --src data/detector_yolo
python -m ml.verify_dataset --data configs/dataset_coarse.yaml
python scripts/train_yolo.py --data configs/dataset_coarse.yaml --model yolo11s.pt
python -m ml.eval_detector --weights outputs/training/ibvap_coarse/weights/best.pt
```

`convert_mot17_to_yolo.py` and `convert_virat.py` stay in `scripts/` (not here) — still the way to
regenerate MOT/VIRAT frames from source if the J: drive is remounted.
