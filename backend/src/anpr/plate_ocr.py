"""
IBVAP — Plate OCR
OCR engine for license plate text extraction using PaddleOCR.
"""

import cv2
import numpy as np
from loguru import logger


class PlateOCR:
    """
    Extracts text from license plate images using PaddleOCR.
    Returns plate text + confidence.
    """

    def __init__(self):
        self._ocr = None
        self._load_ocr()

    def _load_ocr(self):
        try:
            from paddleocr import PaddleOCR

            self._ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
            logger.success("PaddleOCR loaded for ANPR")
        except ImportError:
            logger.warning("PaddleOCR not installed — ANPR OCR disabled")
        except Exception as e:
            logger.error(f"PaddleOCR init error: {e}")

    def read_plate(self, plate_image: np.ndarray) -> tuple[str, float]:
        """
        Read text from a plate crop image.

        Returns:
            (plate_text, confidence)
        """
        if self._ocr is None:
            return ("", 0.0)

        try:
            # Preprocess
            processed = self._preprocess(plate_image)

            # OCR
            results = self._ocr.ocr(processed, cls=True)

            if results and results[0]:
                texts = []
                confidences = []
                for line in results[0]:
                    text = line[1][0]
                    conf = line[1][1]
                    texts.append(text)
                    confidences.append(conf)

                full_text = " ".join(texts).strip().upper()
                avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

                return (full_text, avg_conf)

        except Exception as e:
            logger.error(f"Plate OCR error: {e}")

        return ("", 0.0)

    @staticmethod
    def _preprocess(image: np.ndarray) -> np.ndarray:
        """Preprocess plate image for better OCR accuracy."""
        if image is None or image.size == 0:
            return image

        # Resize if too small
        h, w = image.shape[:2]
        if w < 100:
            scale = 200 / w
            image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        # Convert to grayscale
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Increase contrast
        gray = cv2.equalizeHist(gray)

        # Slight blur to reduce noise
        gray = cv2.GaussianBlur(gray, (3, 3), 0)

        return gray
