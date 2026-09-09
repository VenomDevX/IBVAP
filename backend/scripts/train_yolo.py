"""
train_yolo.py — coarse detector training (IBVAP)
===============================================
Trains the ~13-class coarse detector (see backend/ml/taxonomy.py) on the
leak-free, clip-aware split (configs/dataset_coarse.yaml).

Tuned for a ~6 GB RTX 40-series:  yolo11s @ 640, explicit SGD, disk cache, AMP.
Run  `python -m ml.verify_dataset --data configs/dataset_coarse.yaml`  first.

Windows note — if you hit
    RuntimeError: Couldn't open shared file mapping ... error code: <1455>
that is the OS commit limit (RAM + page file) being exhausted by DataLoader
worker processes. Either:
  * run with `--workers 0`  (no worker processes; a bit slower), or
  * raise the Windows page file: System > Advanced system settings > Performance
    Settings > Advanced > Virtual memory > set a custom size (e.g. 32768 MB).
`--cache disk` (default) also keeps RAM use low; do NOT use `--cache ram` here.

Usage:
  python scripts/train_yolo.py                         # full run, defaults
  python scripts/train_yolo.py --epochs 3 --workers 0  # smoke test, worker-safe
  python scripts/train_yolo.py --resume --model outputs/training/ibvap_coarse/weights/last.pt
"""

import argparse
import os

# cuDNN STREAM_MISMATCH workaround for RTX 40-series
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

from ultralytics import YOLO

DEFAULT_DATA = "configs/dataset_coarse.yaml"
RUN_NAME = "ibvap_coarse"


def train(args):
    data_yaml = os.path.abspath(args.data)
    model_name = os.path.abspath(args.model) if os.path.exists(args.model) else args.model

    print(f"Loading model: {model_name}")
    try:
        model = YOLO(model_name)
    except Exception as e:
        raise SystemExit(
            f"Could not load '{model_name}': {e}\n"
            f"If this is a yolo11 name on old ultralytics, run  pip install -U ultralytics  "
            f"or pass  --model yolov8s.pt"
        )

    if args.resume:
        print(f"RESUMING from {model_name}")
        model.train(resume=True)
        return

    if not os.path.exists(data_yaml):
        raise SystemExit(f"data config not found: {data_yaml} "
                         f"(run scripts/make_clean_split.py first)")

    print(f"data={data_yaml}  epochs={args.epochs}  imgsz={args.imgsz}  "
          f"batch={args.batch}  workers={args.workers}  optimizer={args.optimizer}")
    model.train(
        data=data_yaml,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,            # -1 = auto-fit VRAM
        patience=args.patience,
        device=args.device,
        workers=args.workers,        # 2 is Windows-safe; use 0 on "shared file mapping" errors
        cache=args.cache,
        # --- optimizer: explicit SGD with the well-tuned YOLO fine-tuning schedule
        #     (beats the auto-picked AdamW @ lr~6e-4, which converges very slowly) ---
        optimizer=args.optimizer,
        lr0=args.lr0,
        lrf=0.01,
        momentum=0.937,
        weight_decay=0.0005,
        warmup_epochs=3.0,
        cos_lr=True,
        close_mosaic=15,
        # augmentation — copy_paste/mixup specifically lift the rare military classes
        mixup=0.10,
        copy_paste=0.15,
        degrees=5.0,
        scale=0.5,
        deterministic=False,         # cuDNN STREAM_MISMATCH workaround
        project=args.project,
        name=args.name,
        exist_ok=True,
        plots=True,
    )
    print("\nDone.")
    print(f"  best: {args.project}/{args.name}/weights/best.pt")
    print(f"\nEvaluate:  python -m ml.eval_detector "
          f"--weights outputs/training/{RUN_NAME}/weights/best.pt")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Train the IBVAP coarse detector")
    p.add_argument("--data", default=DEFAULT_DATA)
    p.add_argument("--model", default="yolo11s.pt", help="pretrained name or a checkpoint path")
    p.add_argument("--epochs", type=int, default=150)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--batch", type=int, default=-1, help="-1 = auto-fit VRAM")
    p.add_argument("--patience", type=int, default=40)
    p.add_argument("--device", default="0", help="0 / 0,1 / cpu")
    p.add_argument("--project", default="outputs/training", help="output dir (point at Drive on Colab)")
    p.add_argument("--name", default=RUN_NAME)
    p.add_argument("--workers", type=int, default=2,
                   help="dataloader workers; use 0 on Windows 'shared file mapping' errors")
    p.add_argument("--optimizer", default="SGD", choices=["SGD", "AdamW", "auto"])
    p.add_argument("--lr0", type=float, default=0.01, help="initial LR (0.01 SGD / 0.001 AdamW)")
    p.add_argument("--cache", default="disk", choices=["disk", "ram", "False"])
    p.add_argument("--resume", action="store_true")
    args = p.parse_args()
    if args.cache == "False":
        args.cache = False
    train(args)
