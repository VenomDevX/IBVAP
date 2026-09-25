import cv2
import numpy as np


def get_dominant_color(crop: np.ndarray) -> str:
    """Estimate a broad vehicle body colour, returning Unknown when weak.

    The central ROI reduces road/sky/background pixels; mutually exclusive HSV
    masks and a coverage gate avoid producing a confident label from noise.
    """
    if crop is None or crop.size == 0 or crop.shape[0] < 20 or crop.shape[1] < 20:
        return "Unknown"
    height, width = crop.shape[:2]
    roi = crop[int(height * 0.15) : int(height * 0.88), int(width * 0.1) : int(width * 0.9)]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    hue, saturation, value = cv2.split(hsv)
    masks = {
        "Black": value < 45,
        "White": (saturation < 35) & (value >= 210),
        "Silver": (saturation < 50) & (value >= 145) & (value < 210),
        "Grey": (saturation < 65) & (value >= 45) & (value < 145),
        "Red": (((hue <= 10) | (hue >= 165)) & (saturation >= 65) & (value >= 45)),
        "Brown": ((hue > 5) & (hue <= 25) & (saturation >= 65) & (value >= 35) & (value < 190)),
        "Yellow": ((hue > 20) & (hue <= 38) & (saturation >= 65) & (value >= 80)),
        "Green": ((hue > 38) & (hue <= 88) & (saturation >= 55) & (value >= 40)),
        "Blue": ((hue > 88) & (hue <= 135) & (saturation >= 55) & (value >= 40)),
    }
    counts = {label: int(np.count_nonzero(mask)) for label, mask in masks.items()}
    label, count = max(counts.items(), key=lambda item: item[1])
    coverage = count / max(hue.size, 1)
    return label if coverage >= 0.18 else "Unknown"
