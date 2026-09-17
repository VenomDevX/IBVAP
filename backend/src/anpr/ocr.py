"""
IBVAP — Plate OCR engine

One entry point, `read_plate(crop) -> (text, confidence)`, backed by whichever
engine is available. Preference order (override with `IBVAP_OCR_ENGINE`):

    easyocr  ->  paddleocr  ->  pytesseract  ->  unavailable

The engine is loaded lazily on first call (model download can be slow) and reused.
"""

import os
import re
import threading

import cv2
import numpy as np
from loguru import logger

_PLATE_RE = re.compile(r"[^A-Z0-9]")
_MIN_LEN = 4
_MAX_LEN = 12
UPSCALE_WIDTH = int(os.getenv("IBVAP_OCR_UPSCALE_WIDTH", "200"))

_lock = threading.Lock()
# EasyOCR/Paddle readers are not thread-safe; the enrichment pool calls
# read_plate() from several threads, so inference is serialised separately.
_infer_lock = threading.Lock()
_reader = None
_engine_name = "uninitialised"


def _normalise(text: str) -> str:
    return _PLATE_RE.sub("", (text or "").upper())


def _preprocess(img: np.ndarray, enhance: bool = False) -> np.ndarray:
    if img is None or img.size == 0:
        return img
    h, w = img.shape[:2]
    # Recognition models do much better on small CCTV plates once upscaled.
    if w < UPSCALE_WIDTH:
        scale = UPSCALE_WIDTH / max(w, 1)
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    # Grayscale + CLAHE helps tesseract; PaddleOCR reads the colour crop better
    # (78% -> 81% exact on the synthetic Indian plate set, scripts/eval_anpr.py).
    if not enhance:
        return img
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    return gray


# --------------------------------------------------------------------------- #
# Engine adapters — each returns (raw_text, confidence) or ("", 0.0)
# --------------------------------------------------------------------------- #


def _easyocr_reader():
    import easyocr

    return easyocr.Reader(["en"], gpu=False, verbose=False)


def _read_easyocr(reader, img):
    res = reader.readtext(img, detail=1, paragraph=False)
    if not res:
        return "", 0.0
    # pick the highest-confidence line
    best = max(res, key=lambda r: r[2])
    return best[1], float(best[2])


def _paddle_reader():
    from paddleocr import PaddleOCR

    try:
        # PaddleOCR 3.x. oneDNN is off: paddlepaddle 3.3 on Windows CPU fails with
        # "ConvertPirAttribute2RuntimeAttribute not support" when it is on.
        return PaddleOCR(
            lang="en",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            enable_mkldnn=False,
        )
    except (TypeError, ValueError):
        return PaddleOCR(use_angle_cls=True, lang="en", show_log=False)  # 2.x


def _read_paddle(reader, img):
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if hasattr(reader, "predict"):  # 3.x
        results = reader.predict(img)
        if not results:
            return "", 0.0
        result = results[0]
        lines = list(zip(result["rec_texts"], result["rec_scores"], result["rec_polys"]))
    else:  # 2.x
        raw = reader.ocr(img, cls=True)
        if not raw or not raw[0]:
            return "", 0.0
        lines = [(line[1][0], line[1][1], line[0]) for line in raw[0]]
    lines = [(text, float(score), poly) for text, score, poly in lines if text and score > 0.3]
    if not lines:
        return "", 0.0
    # Two-row plates (common on Indian two-wheelers): read top row first.
    lines.sort(key=lambda item: (round(float(np.mean(np.asarray(item[2])[:, 1])) / 12), np.min(np.asarray(item[2])[:, 0])))
    text = "".join(item[0] for item in lines)
    weight = sum(len(item[0]) for item in lines)
    confidence = sum(item[1] * len(item[0]) for item in lines) / max(weight, 1)
    return text, confidence


def _tesseract_reader():
    import pytesseract  # noqa: F401

    return "pytesseract"


def _read_tesseract(_reader, img):
    import pytesseract

    text = pytesseract.image_to_string(img, config="--psm 8")
    return text, 0.5 if text.strip() else 0.0


_ENGINES = [
    ("easyocr", _easyocr_reader, _read_easyocr),
    ("paddleocr", _paddle_reader, _read_paddle),
    ("pytesseract", _tesseract_reader, _read_tesseract),
]


def _init() -> None:
    global _reader, _engine_name
    if _reader is not None or _engine_name == "unavailable":
        return
    forced = os.getenv("IBVAP_OCR_ENGINE", "").strip().lower()
    order = [e for e in _ENGINES if not forced or e[0] == forced]
    for name, build, _read in order:
        try:
            _reader = build()
            _engine_name = name
            logger.success(f"ANPR OCR engine: {name}")
            return
        except ImportError:
            continue
        except Exception as e:  # noqa: BLE001
            logger.warning(f"ANPR OCR engine {name} failed to load: {e}")
    _engine_name = "unavailable"
    logger.warning("ANPR OCR unavailable: install/configure a supported OCR engine")


def read_plate(crop: np.ndarray) -> tuple[str, float]:
    """Return (plate_text, confidence 0-1). ('', 0.0) if nothing legible."""
    if crop is None or getattr(crop, "size", 0) == 0:
        return "", 0.0

    with _lock:
        _init()
        engine, reader = _engine_name, _reader

    if engine == "unavailable":
        return "", 0.0

    reader_fn = next(r for n, _b, r in _ENGINES if n == engine)
    try:
        img = _preprocess(crop, enhance=engine in ("pytesseract", "easyocr"))
        with _infer_lock:
            raw, conf = reader_fn(reader, img)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"ANPR OCR error ({engine}): {e}")
        return "", 0.0

    text = _normalise(raw)
    if _MIN_LEN <= len(text) <= _MAX_LEN:
        return text, round(conf, 3)
    return "", 0.0


def engine_name() -> str:
    with _lock:
        _init()
        return _engine_name
