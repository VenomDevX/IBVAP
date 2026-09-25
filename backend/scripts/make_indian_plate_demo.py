"""
make_indian_plate_demo.py — build a demo video with Indian number plates.

None of the demo clips has readable Indian plates (the only clip with legible
plates, scooter_traffic_intersection.mp4, is Vietnamese traffic). This script
keeps that real footage and paints a rendered Indian plate over every plate the
detector finds, following each plate across frames so one vehicle keeps one
number. The result is SYNTHETIC: real traffic and motion, generated plates.

  python scripts/make_indian_plate_demo.py
  -> data/demo/indian_plates_synthetic.mp4
     data/demo/indian_plates_synthetic.json   (ground truth: plate numbers)
"""

import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

PLATE_CLASS_ID = 6
STATES = ["MH", "DL", "KA", "UP", "WB", "TN", "RJ", "GJ", "HR", "PB", "BR", "AS"]
LETTERS = "ABCDEFGHJKLMNPRSTUVWXYZ"
# The longest-visible vehicle gets a fixed number so it can be put on a watchlist in a demo.
FIRST_PLATE = "MH12AB3456"


def plate_number(rng: random.Random) -> str:
    return (
        f"{rng.choice(STATES)}{rng.randint(1, 99):02d}"
        f"{''.join(rng.choice(LETTERS) for _ in range(2))}{rng.randint(1, 9999):04d}"
    )


def split_rows(text: str, two_row: bool) -> list[str]:
    state, district, series, number = text[:2], text[2:4], text[4:-4], text[-4:]
    if two_row:
        return [f"{state} {district} {series}", number]
    return [f"{state} {district} {series} {number}"]


def render_plate(rows: list[str], width: int, height: int) -> np.ndarray:
    """Black-on-white plate drawn large, then resized to the target box."""
    font, thickness, scale = cv2.FONT_HERSHEY_DUPLEX, 4, 2.2
    sizes = [cv2.getTextSize(r, font, scale, thickness)[0] for r in rows]
    big_w = max(w for w, _ in sizes) + 60
    row_h = max(h for _, h in sizes) + 30
    big_h = row_h * len(rows) + 20
    plate = np.full((big_h, big_w, 3), 245, np.uint8)
    cv2.rectangle(plate, (4, 4), (big_w - 5, big_h - 5), (20, 20, 20), 5)
    for i, (row, (w, h)) in enumerate(zip(rows, sizes)):
        cv2.putText(
            plate, row, ((big_w - w) // 2, 10 + row_h * i + h + 12), font, scale, (15, 15, 15), thickness, cv2.LINE_AA
        )
    return cv2.resize(plate, (width, height), interpolation=cv2.INTER_AREA)


def paste(frame: np.ndarray, box, patch: np.ndarray) -> None:
    x1, y1, x2, y2 = box
    h, w = y2 - y1, x2 - x1
    # Match the scene's brightness so the plate doesn't glow at night / in shade.
    region = frame[y1:y2, x1:x2].astype(np.float32)
    patch = patch.astype(np.float32) * np.clip(region.mean() / 150.0, 0.55, 1.0)
    mask = np.ones((h, w), np.float32)
    feather = max(1, min(h, w) // 10)
    mask = cv2.GaussianBlur(
        np.pad(mask[feather : -feather or None, feather : -feather or None], feather, constant_values=0),
        (0, 0),
        feather / 2,
    )[:h, :w, None]
    frame[y1:y2, x1:x2] = (patch * mask + region * (1 - mask)).astype(np.uint8)


def iou(a, b) -> float:
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="data/demo/scooter_traffic_intersection.mp4")
    ap.add_argument("--output", default="data/demo/indian_plates_synthetic.mp4")
    ap.add_argument("--weights", default="models/ibvap_coarse.pt")
    ap.add_argument("--conf", type=float, default=0.15)
    ap.add_argument("--hold-frames", type=int, default=12, help="follow a plate through this many missed frames")
    ap.add_argument("--seed", type=int, default=2026)
    # The lanes where traffic drives toward the camera. A 1080p crop makes plates
    # twice as large to the 640 px detector as the full 4K frame does.
    ap.add_argument("--crop", default="1920,1080,1920,1080", help="x,y,w,h in source pixels; '' for full frame")
    args = ap.parse_args()

    from ultralytics import YOLO

    model = YOLO(args.weights)
    rng = random.Random(args.seed)
    cap = cv2.VideoCapture(args.source)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    crop = tuple(int(v) for v in args.crop.split(",")) if args.crop else (0, 0, width, height)
    cx, cy, width, height = crop

    def read(capture):
        ok, full = capture.read()
        return ok, (full[cy : cy + height, cx : cx + width].copy() if ok else None)

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Pass 1: detect and track plates (boxes per frame per track).
    tracks, index = [], 0  # track: {id, boxes{frame: box}, last, velocity, missed}
    while True:
        ok, frame = read(cap)
        if not ok:
            break
        boxes = []
        for b in model(frame, conf=args.conf, imgsz=960, verbose=False)[0].boxes:
            if int(b.cls) == PLATE_CLASS_ID:
                x1, y1, x2, y2 = (int(v) for v in b.xyxy[0].tolist())
                if x2 - x1 >= 24 and y2 - y1 >= 10:
                    boxes.append((max(0, x1), max(0, y1), min(width, x2), min(height, y2)))
        live = [t for t in tracks if t["missed"] <= args.hold_frames]
        taken = set()
        for box in boxes:
            candidates = [t for t in live if t["id"] not in taken]
            best = max(candidates, key=lambda t: iou(_predict(t), box), default=None)
            if best is not None and iou(_predict(best), box) > 0.1:
                gap = best["missed"] + 1
                best["velocity"] = tuple((n - o) / gap for n, o in zip(box, best["last"]))
                best.update(last=box, missed=0)
                best["boxes"][index] = box
                best["detections"] += 1
                taken.add(best["id"])
            else:
                track = {
                    "id": len(tracks),
                    "boxes": {index: box},
                    "last": box,
                    "velocity": (0, 0, 0, 0),
                    "missed": 0,
                    "detections": 1,
                    "first_frame": index,
                    "two_row": (box[3] - box[1]) / max(1, box[2] - box[0]) > 0.45,
                }
                tracks.append(track)
                taken.add(track["id"])
        for track in live:
            if track["id"] not in taken:
                track["missed"] += 1
                if track["missed"] <= args.hold_frames:
                    # Short detector gap: keep following the plate at its last speed.
                    predicted = tuple(int(v) for v in _predict(track))
                    if predicted[2] - predicted[0] > 4 and predicted[3] - predicted[1] > 4:
                        track["boxes"][index] = predicted
        index += 1
        if index % 100 == 0:
            print(f"pass 1: {index}/{total} frames, {len(tracks)} plates", flush=True)
    cap.release()

    # Plate numbers: the longest-visible vehicle gets the fixed watchlist-demo number.
    visible = [t for t in tracks if t["detections"] >= 5]
    for track in tracks:
        track["plate"] = plate_number(rng)
    if visible:
        max(visible, key=lambda t: t["detections"])["plate"] = FIRST_PLATE

    # Pass 2: paint.
    by_frame: dict[int, list] = {}
    for track in tracks:
        for frame_index, box in track["boxes"].items():
            by_frame.setdefault(frame_index, []).append((box, track))
    cap = cv2.VideoCapture(args.source)
    writer = cv2.VideoWriter(args.output, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    for frame_index in range(index):
        ok, frame = read(cap)
        if not ok:
            break
        for box, track in by_frame.get(frame_index, []):
            x1, y1 = max(0, box[0]), max(0, box[1])
            x2, y2 = min(width, box[2]), min(height, box[3])
            if x2 - x1 > 4 and y2 - y1 > 4:
                paste(
                    frame,
                    (x1, y1, x2, y2),
                    render_plate(split_rows(track["plate"], track["two_row"]), x2 - x1, y2 - y1),
                )
        writer.write(frame)
    writer.release()
    cap.release()

    truth = {
        "synthetic": True,
        "source": os.path.basename(args.source),
        "crop": list(crop),
        "note": "Real traffic footage; plates replaced with rendered Indian plates.",
        "watchlist_demo_plate": FIRST_PLATE if visible else None,
        "plates": [
            {
                "plate": t["plate"],
                "two_row": t["two_row"],
                "first_frame": t["first_frame"],
                "detections": t["detections"],
                "painted_frames": len(t["boxes"]),
            }
            for t in sorted(visible, key=lambda t: t["first_frame"])
        ],
    }
    with open(os.path.splitext(args.output)[0] + ".json", "w", encoding="utf-8") as fh:
        json.dump(truth, fh, indent=2)
    print(f"wrote {args.output}: {index} frames, {len(visible)} plates detected in 5+ frames")


def _predict(track):
    gap = track["missed"] + 1
    return tuple(o + v * gap for o, v in zip(track["last"], track["velocity"]))


if __name__ == "__main__":
    main()
