"""
train_yolo.py — coarse detector training (IBVAP)
===============================================
Trains the 13-class coarse detector (see backend/ml/taxonomy.py) on the
deduplicated, rare-class-preserving release set built by
`python scripts/build_dataset.py` -> data/dataset/detector/dataset.yaml.

Tuned for a ~6 GB RTX 40-series (RTX 4050 Laptop): yolo11s @ 640, batch 4,
explicit SGD, AMP, no image cache. Warm-starts from models/ibvap_coarse.pt.

Measured on that card: batch 8 CUDA-OOMs (only ~5.2 GB is free once Windows
takes its share), and `--cache disk` wants 140 GB for this 47.5k train split.

Measure before you commit a night to it:
    python scripts/train_yolo.py --benchmark
prints real minutes/epoch on this machine and the epochs that fit your budget.

Windows note — if you hit
    RuntimeError: Couldn't open shared file mapping ... error code: <1455>
that is the OS commit limit (RAM + page file) being exhausted by DataLoader
worker processes. Either:
  * run with `--workers 0`  (no worker processes; a bit slower), or
  * raise the Windows page file: System > Advanced system settings > Performance
    Settings > Advanced > Virtual memory > set a custom size (e.g. 32768 MB).
Image caching is OFF by default here; `--cache ram` will not fit either.

Usage:
  python scripts/train_yolo.py --benchmark             # 1 epoch, report min/epoch
  python scripts/train_yolo.py --epochs 48             # full run
  python scripts/train_yolo.py --epochs 3 --workers 0  # smoke test, worker-safe
  python scripts/train_yolo.py --resume --model outputs/training/ibvap_coarse/weights/last.pt

Overnight runs should go through scripts/run_training.ps1, which restarts and
resumes automatically after a transient CUDA fault.
"""

import argparse
import os
import time

# cuDNN STREAM_MISMATCH workaround for RTX 40-series
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

# 6 GB is small enough that allocator fragmentation, not total size, is what
# kills a run: a batch-8 attempt died trying to allocate 14 MiB while 3.45 GiB
# was still free. Expandable segments let the allocator grow a block instead of
# demanding one contiguous span.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

from ultralytics import YOLO

DEFAULT_DATA = "data/dataset/detector/dataset.yaml"
RUN_NAME = "ibvap_coarse"


def _preflight(args) -> None:
    """Report free VRAM and system RAM before committing to a long run.

    Both have already broken this training: batch=8 hit a CUDA OOM with 5.2GB
    free (fragmentation), and label scanning hit a plain MemoryError with 2GB
    of system RAM left because other applications were holding the rest.
    """
    try:
        import torch

        if torch.cuda.is_available():
            free_b, total_b = torch.cuda.mem_get_info()
            free, total = free_b / 2**30, total_b / 2**30
            print(f"GPU: {torch.cuda.get_device_name(0)}  {free:.1f}/{total:.1f} GiB free")
            need = {4: 2.6, 6: 3.6, 8: 4.6}.get(args.batch, 0.55 * args.batch)
            if free < need:
                print(
                    f"  WARNING: batch={args.batch} needs roughly {need:.1f} GiB and only "
                    f"{free:.1f} GiB is free. Close other GPU apps or lower --batch."
                )
        else:
            print("GPU: none visible — training on CPU would take weeks. Stopping.")
            raise SystemExit(1)
    except ImportError:
        pass

    try:
        import shutil

        import psutil

        ram = psutil.virtual_memory().available / 2**30
        print(f"RAM: {ram:.1f} GiB available")
        if ram < 4:
            print(
                "  WARNING: under 4 GiB free. Label scanning raises a plain MemoryError "
                "at this level — close other applications before starting."
            )
        free_disk = shutil.disk_usage(".").free / 2**30
        print(f"Disk: {free_disk:.0f} GiB free")
    except ImportError:
        pass


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
        raise SystemExit(f"data config not found: {data_yaml} (run scripts/build_dataset.py first)")

    if args.batch == -1:
        print(
            "WARNING: --batch -1 (autobatch) probes VRAM at startup and can pick a size\n"
            "         that OOMs later once activations peak, killing an overnight run.\n"
            "         On a 6GB card use --batch 4."
        )

    _preflight(args)

    if args.benchmark:
        args.epochs = 1
        print("BENCHMARK: one epoch, then report minutes/epoch and exit.")
    t0 = time.time()

    print(
        f"data={data_yaml}  epochs={args.epochs}  imgsz={args.imgsz}  "
        f"batch={args.batch}  workers={args.workers}  optimizer={args.optimizer}"
    )
    model.train(
        data=data_yaml,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,  # -1 = auto-fit VRAM
        patience=args.patience,
        device=args.device,
        workers=args.workers,  # 2 is Windows-safe; use 0 on "shared file mapping" errors
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
        deterministic=False,  # cuDNN STREAM_MISMATCH workaround
        # Absolute, or ultralytics resolves it under its own settings runs_dir
        # and results land in runs/detect/outputs/training/... instead.
        project=os.path.abspath(args.project),
        name=args.name,
        exist_ok=True,
        plots=True,
    )
    if args.benchmark:
        mins = (time.time() - t0) / 60
        print(f"\n=== BENCHMARK: {mins:.1f} min/epoch on this machine ===")
        print("    Pick --epochs from your budget:")
        for budget in (12, 20, 24):
            print(f"      {budget:>2}h  ->  {int(budget * 60 / mins)} epochs")
        if mins > 40:
            print(
                "\n    Over 40 min/epoch. Fallback ladder, in order:\n"
                "      1. python scripts/build_dataset.py --force rebalance "
                "--target-detector 40000\n"
                "      2. --imgsz 576   (give up resolution LAST: it costs the most\n"
                "         accuracy on the distant objects this system exists to spot)"
            )
        return

    print("\nDone.")
    print(f"  best: {args.project}/{args.name}/weights/best.pt")
    print(f"\nEvaluate:  python -m ml.eval_detector --weights outputs/training/{RUN_NAME}/weights/best.pt")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Train the IBVAP coarse detector")
    p.add_argument("--data", default=DEFAULT_DATA)
    p.add_argument(
        "--model",
        default="models/ibvap_coarse.pt",
        help="warm-start checkpoint, or a pretrained name like yolo11s.pt",
    )
    p.add_argument("--epochs", type=int, default=48)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument(
        "--batch",
        type=int,
        default=4,
        help="explicit batch size. Do NOT use -1 on a 6GB card: autobatch probes "
        "VRAM at startup and can pick a size that OOMs hours later. batch=8 was "
        "measured to OOM on a 6GB RTX 4050 (only ~5.2GB free after Windows).",
    )
    p.add_argument(
        "--benchmark",
        action="store_true",
        help="train exactly one epoch, report min/epoch, and exit",
    )
    p.add_argument("--patience", type=int, default=40)
    p.add_argument("--device", default="0", help="0 / 0,1 / cpu")
    p.add_argument("--project", default="outputs/training", help="output dir (point at Drive on Colab)")
    p.add_argument("--name", default=RUN_NAME)
    p.add_argument(
        "--workers", type=int, default=2, help="dataloader workers; use 0 on Windows 'shared file mapping' errors"
    )
    p.add_argument("--optimizer", default="SGD", choices=["SGD", "AdamW", "auto"])
    p.add_argument("--lr0", type=float, default=0.01, help="initial LR (0.01 SGD / 0.001 AdamW)")
    p.add_argument(
        "--cache",
        default="False",
        choices=["disk", "ram", "False"],
        help="disk caching wants 140GB for this 47.5k-image train split "
        "(measured) and only ~82GB is free, so it silently declines for train "
        "while still writing 8.7GB for val. Off by default; the source images "
        "are already on a local SSD.",
    )
    p.add_argument("--resume", action="store_true")
    args = p.parse_args()
    if args.cache == "False":
        args.cache = False
    train(args)
