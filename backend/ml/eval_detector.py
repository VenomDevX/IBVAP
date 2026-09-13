"""
eval_detector.py — per-class evaluation of the coarse detector
=============================================================
"Best accuracy" means tuning against the PER-CLASS table, not the aggregate mAP.
This runs YOLO validation and prints instances / P / R / mAP@50 / mAP@50-95 per
class, and drops the confusion matrix + PR curves under outputs/eval/<run>/.

Usage:
  python -m ml.eval_detector --weights outputs/training/ibvap_coarse/weights/best.pt
  python -m ml.eval_detector --weights .../best.pt --data configs/dataset_coarse.yaml --imgsz 640
"""

from __future__ import annotations

import argparse
import json
import os

from ultralytics import YOLO

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True)
    ap.add_argument("--data", default=os.path.join(BACKEND, "configs", "dataset_coarse.yaml"))
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--split", default="val", choices=["val", "test", "train"])
    ap.add_argument("--conf", type=float, default=0.001)  # low conf for honest mAP
    ap.add_argument("--device", default="0")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--tta", action="store_true", help="test-time augmentation (slower, ~+1 mAP)")
    args = ap.parse_args()

    weights = os.path.abspath(args.weights)
    if not os.path.exists(weights):
        raise SystemExit(f"weights not found: {weights}")
    run = os.path.basename(os.path.dirname(os.path.dirname(weights))) or "eval"
    out_dir = os.path.join(BACKEND, "outputs", "eval")

    model = YOLO(weights)
    m = model.val(
        data=os.path.abspath(args.data),
        split=args.split,
        imgsz=args.imgsz,
        conf=args.conf,
        device=args.device,
        batch=args.batch,
        augment=args.tta,
        plots=True,
        save_json=True,
        project=out_dir,
        name=run,
        exist_ok=True,
    )

    names = model.names  # {id: name}
    print("\n" + "=" * 78)
    print(f"{'id':>3}  {'class':22s} {'images':>7} {'inst':>8} {'P':>7} {'R':>7} {'mAP50':>8} {'mAP50-95':>9}")
    print("-" * 78)
    # per-class arrays live on m.box; ap_class_index maps row -> class id
    try:
        idx = list(m.box.ap_class_index)
        p, r = m.box.p, m.box.r
        ap50, ap = m.box.ap50, m.box.ap
        per_class = []
        for row, cid in enumerate(idx):
            per_class.append({
                "id": int(cid), "class": str(names[cid]),
                "precision": float(p[row]), "recall": float(r[row]),
                "map50": float(ap50[row]), "map50_95": float(ap[row]),
            })
            print(
                f"{cid:>3}  {str(names[cid]):22s} {'-':>7} "
                f"{'-':>8} {p[row]:7.3f} {r[row]:7.3f} {ap50[row]:8.3f} {ap[row]:9.3f}"
            )
    except Exception as e:
        per_class = []
        print(f"(per-class array unpack failed: {e}; see the CSV/plots in {out_dir}/{run})")
    print("-" * 78)
    print(f"{'':3}  {'ALL':22s} {'':>7} {'':>8} {m.box.mp:7.3f} {m.box.mr:7.3f} {m.box.map50:8.3f} {m.box.map:9.3f}")
    print("=" * 78)
    result_dir = os.path.join(out_dir, run)
    with open(os.path.join(result_dir, "metrics.json"), "w", encoding="utf-8") as fh:
        json.dump({
            "weights": weights, "split": args.split, "imgsz": args.imgsz,
            "precision": float(m.box.mp), "recall": float(m.box.mr),
            "map50": float(m.box.map50), "map50_95": float(m.box.map),
            "per_class": per_class,
        }, fh, indent=2)
    print(f"\nplots + confusion matrix + predictions.json + metrics.json -> {result_dir}")
    print("Weak classes (low mAP50): add data / raise imgsz / bump copy_paste, then retrain.")


if __name__ == "__main__":
    main()
