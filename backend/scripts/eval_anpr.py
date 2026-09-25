"""
eval_anpr.py — end-to-end ANPR check on labelled validation images.

For validation images that contain a license_plate box, runs the real chain
(coarse detector -> plate crop -> OCR -> Indian plate grammar) and reports how
many plates were found, read, and fit a valid format. The dataset has boxes,
not plate text, so reading accuracy is judged from the saved crops.

  python scripts/eval_anpr.py --limit 200 --save-crops outputs/eval/anpr

The training plates are mostly Vietnamese, so `--synthetic N` also renders N
Indian plates with known text (standard, BH series, two-row two-wheeler
layout; perspective, blur, noise) and reports exact-match accuracy of
OCR + grammar. Synthetic plates are a sanity check, not proof of real-world
Indian accuracy.
"""

import argparse
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import cv2  # noqa: E402
import yaml  # noqa: E402

from src.anpr.ocr import engine_name, read_plate  # noqa: E402
from src.anpr.plate_assign import _crop  # noqa: E402
from src.anpr.plate_format import parse_plate  # noqa: E402
from src.paths import backend_path  # noqa: E402

PLATE_CLASS_ID = 6


def plate_images(split_file: str) -> list[str]:
    images = []
    with open(split_file, encoding="utf-8") as fh:
        for line in fh:
            image = line.strip()
            label = (
                os.path.splitext(
                    image.replace(f"{os.sep}images{os.sep}", f"{os.sep}labels{os.sep}").replace("/images/", "/labels/")
                )[0]
                + ".txt"
            )
            try:
                with open(label, encoding="utf-8") as lf:
                    if any(row.split()[:1] == [str(PLATE_CLASS_ID)] for row in lf):
                        images.append(image)
            except OSError:
                continue
    return images


STATES = ["MH", "DL", "KA", "UP", "WB", "TN", "RJ", "GJ", "BR", "AS", "PB", "HR"]
LETTERS = "ABCDEFGHJKLMNPRSTUVWXYZ"


def _random_plate(rng: random.Random) -> tuple[str, list[str]]:
    kind = rng.random()
    number = f"{rng.randint(1, 9999):04d}"
    if kind < 0.15:
        year = f"{rng.randint(21, 26)}"
        series = "".join(rng.choice(LETTERS) for _ in range(rng.choice((1, 2))))
        text = f"{year}BH{number}{series}"
        return text, [f"{year} BH {number} {series}"]
    state = rng.choice(STATES)
    district = f"{rng.randint(1, 99):02d}"
    series = "".join(rng.choice(LETTERS) for _ in range(rng.choice((1, 2, 2, 2))))
    text = f"{state}{district}{series}{number}"
    if kind < 0.35:  # two-row two-wheeler plate
        return text, [f"{state} {district} {series}", number]
    return text, [f"{state} {district} {series} {number}"]


def _render(rows: list[str], rng: random.Random):
    import numpy as np

    font, thickness = cv2.FONT_HERSHEY_DUPLEX, 3
    scale = 1.6
    sizes = [cv2.getTextSize(r, font, scale, thickness)[0] for r in rows]
    width = max(w for w, _ in sizes) + 40
    row_h = max(h for _, h in sizes) + 22
    height = row_h * len(rows) + 16
    background = (255, 255, 255) if rng.random() < 0.7 else (0, 200, 255)  # white private / yellow commercial
    plate = np.full((height, width, 3), background, np.uint8)
    cv2.rectangle(plate, (3, 3), (width - 4, height - 4), (0, 0, 0), 3)
    for i, (row, (w, h)) in enumerate(zip(rows, sizes)):
        cv2.putText(
            plate, row, ((width - w) // 2, 8 + row_h * i + h + 8), font, scale, (0, 0, 0), thickness, cv2.LINE_AA
        )
    # Perspective + scale down to CCTV size + blur + noise, on a dark bumper.
    canvas = np.full((height + 40, width + 40, 3), rng.randint(20, 90), np.uint8)
    canvas[20 : 20 + height, 20 : 20 + width] = plate
    h2, w2 = canvas.shape[:2]
    jitter = lambda: rng.uniform(-0.06, 0.06)  # noqa: E731
    src = np.float32([[0, 0], [w2, 0], [w2, h2], [0, h2]])
    dst = np.float32(
        [
            [w2 * jitter(), h2 * jitter()],
            [w2 * (1 + jitter()), h2 * jitter()],
            [w2 * (1 + jitter()), h2 * (1 + jitter())],
            [w2 * jitter(), h2 * (1 + jitter())],
        ]
    )
    canvas = cv2.warpPerspective(
        canvas, cv2.getPerspectiveTransform(src, dst), (w2, h2), borderMode=cv2.BORDER_REPLICATE
    )
    # Real CCTV plates are often 60-120 px wide, smeared and heavily compressed.
    target_w = rng.randint(60, 180)
    canvas = cv2.resize(canvas, (target_w, max(1, int(h2 * target_w / w2))), interpolation=cv2.INTER_AREA)
    if rng.random() < 0.6:
        canvas = cv2.GaussianBlur(canvas, (3, 3), rng.uniform(0.4, 1.2))
    if rng.random() < 0.35:
        k = rng.choice((3, 5))
        kernel = np.zeros((k, k), np.float32)
        kernel[k // 2, :] = 1.0 / k
        canvas = cv2.filter2D(canvas, -1, kernel)
    dim = rng.uniform(0.45, 1.0)
    noise = np.random.default_rng(rng.randint(0, 10**6)).normal(0, rng.uniform(3, 14), canvas.shape)
    canvas = np.clip(canvas.astype(np.float32) * dim + noise, 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", canvas, [cv2.IMWRITE_JPEG_QUALITY, rng.randint(25, 70)])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def synthetic_eval(count: int, save_dir: str) -> dict:
    rng = random.Random(7)
    exact = raw_exact = valid = 0
    misses = []
    started = time.time()
    for index in range(count):
        truth, rows = _random_plate(rng)
        image = _render(rows, rng)
        text, _conf = read_plate(image)
        reading = parse_plate(text)
        raw_exact += text == truth
        valid += reading.valid
        if reading.valid and reading.text == truth:
            exact += 1
        else:
            misses.append({"truth": truth, "ocr": text, "parsed": reading.text if reading.valid else None})
            if save_dir and len(misses) <= 30:
                cv2.imwrite(os.path.join(save_dir, f"synth_miss_{index:03d}_{truth}.jpg"), image)
    return {
        "synthetic_plates": count,
        "exact_after_grammar": exact,
        "exact_raw_ocr": raw_exact,
        "valid_format": valid,
        "accuracy": round(exact / max(count, 1), 3),
        "seconds": round(time.time() - started, 1),
        "misses": misses[:15],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="configs/dataset_coarse.yaml")
    ap.add_argument("--weights", default="models/ibvap_coarse.pt")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--conf", type=float, default=0.22)
    ap.add_argument("--save-crops", default="")
    ap.add_argument("--synthetic", type=int, default=0, help="also score N synthetic Indian plates")
    args = ap.parse_args()
    if args.save_crops:
        os.makedirs(args.save_crops, exist_ok=True)
    if args.synthetic:
        report = synthetic_eval(args.synthetic, args.save_crops)
        print(json.dumps(report, indent=2))
        if args.limit == 0:
            return

    from ultralytics import YOLO

    with open(backend_path(args.data), encoding="utf-8") as fh:
        split = yaml.safe_load(fh)["val"]
    images = plate_images(split)
    random.Random(42).shuffle(images)
    images = images[: args.limit]
    model = YOLO(str(backend_path(args.weights)))
    print(f"OCR engine: {engine_name()}  images with labelled plates: {len(images)}")
    if args.save_crops:
        os.makedirs(args.save_crops, exist_ok=True)

    found = read = valid = 0
    samples, started = [], time.time()
    for index, path in enumerate(images):
        frame = cv2.imread(path)
        if frame is None:
            continue
        result = model(frame, conf=args.conf, verbose=False)[0]
        plates = [b for b in result.boxes if int(b.cls) == PLATE_CLASS_ID]
        if not plates:
            continue
        found += 1
        best = max(plates, key=lambda b: float(b.conf))
        bbox = tuple(int(v) for v in best.xyxy[0].tolist())
        crop = _crop(frame, bbox)
        text, conf = read_plate(crop)
        reading = parse_plate(text)
        read += bool(text)
        valid += reading.valid
        if args.save_crops and len(samples) < 60:
            name = f"{index:04d}_{reading.text if reading.valid else 'X_' + (text or 'none')}.jpg"
            cv2.imwrite(os.path.join(args.save_crops, name), crop)
        samples.append(
            {
                "image": os.path.basename(path),
                "raw": text,
                "conf": conf,
                "plate": reading.text,
                "format": reading.kind,
                "fixes": reading.corrections,
            }
        )

    n = len(images)
    summary = {
        "images": n,
        "plate_detected": found,
        "ocr_text": read,
        "valid_indian_format": valid,
        "seconds": round(time.time() - started, 1),
        "ocr_engine": engine_name(),
    }
    print(json.dumps(summary, indent=2))
    for s in samples[:25]:
        print(f"  {s['raw']!s:16} -> {s['plate']:12} {s['format']:9} fixes={s['fixes']} conf={s['conf']}")
    if args.save_crops:
        with open(os.path.join(args.save_crops, "results.json"), "w", encoding="utf-8") as fh:
            json.dump({"summary": summary, "samples": samples}, fh, indent=1)


if __name__ == "__main__":
    main()
