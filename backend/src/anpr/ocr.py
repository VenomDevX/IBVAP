"""
IBVAP — Plate OCR engine

One entry point, `read_plate(crop) -> (text, confidence)`, backed by whichever
engine is available. Preference order (override with `IBVAP_OCR_ENGINE`):

    easyocr  ->  paddleocr  ->  pytesseract  ->  mock

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

_lock = threading.Lock()
_reader = None
_engine_name = "uninitialised"


def _normalise(text: str) -> str:
    return _PLATE_RE.sub("", (text or "").upper())


def _preprocess(img: np.ndarray) -> np.ndarray:
    if img is None or img.size == 0:
        return img
    h, w = img.shape[:2]
    if w < 160:
        scale = 200 / max(w, 1)
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
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

    return PaddleOCR(use_angle_cls=True, lang="en", show_log=False)


def _read_paddle(reader, img):
    res = reader.ocr(img, cls=True)
    if not res or not res[0]:
        return "", 0.0
    best = max(res[0], key=lambda line: line[1][1])
    return best[1][0], float(best[1][1])


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
    if _reader is not None or _engine_name == "mock":
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
    _engine_name = "mock"
    logger.warning("ANPR OCR: no engine available — plates report MOCK-PLT")


def read_plate(crop: np.ndarray) -> tuple[str, float]:
    """Return (plate_text, confidence 0-1). ('', 0.0) if nothing legible."""
    if crop is None or getattr(crop, "size", 0) == 0:
        return "", 0.0

    with _lock:
        _init()
        engine, reader = _engine_name, _reader

    if engine == "mock":
        return "MOCK-PLT", 0.0

    reader_fn = next(r for n, _b, r in _ENGINES if n == engine)
    try:
        raw, conf = reader_fn(reader, _preprocess(crop))
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
