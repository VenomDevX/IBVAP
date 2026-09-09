import cv2
import numpy as np

# Basic color boundaries in HSV
COLORS = {
    "Red": ([0, 50, 50], [10, 255, 255]),
    "Orange": ([11, 50, 50], [25, 255, 255]),
    "Yellow": ([26, 50, 50], [35, 255, 255]),
    "Green": ([36, 50, 50], [89, 255, 255]),
    "Blue": ([90, 50, 50], [128, 255, 255]),
    "Purple": ([129, 50, 50], [158, 255, 255]),
    "White": ([0, 0, 200], [180, 50, 255]),
    "Black": ([0, 0, 0], [180, 255, 30]),
    "Gray": ([0, 0, 31], [180, 50, 199]),
}


def get_dominant_color(crop: np.ndarray) -> str:
    """Extract dominant color from a cropped BGR image."""
    if crop is None or crop.size == 0:
        return "Unknown"

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)

    max_pixels = 0
    dominant_color = "Unknown"

    for color_name, (lower, upper) in COLORS.items():
        lower_np = np.array(lower, dtype=np.uint8)
        upper_np = np.array(upper, dtype=np.uint8)

        mask = cv2.inRange(hsv, lower_np, upper_np)
        pixels = cv2.countNonZero(mask)

        if pixels > max_pixels:
            max_pixels = pixels
            dominant_color = color_name

    # Fallback for red wrap-around in HSV
    lower_red2 = np.array([160, 50, 50], dtype=np.uint8)
    upper_red2 = np.array([180, 255, 255], dtype=np.uint8)
    mask_red2 = cv2.inRange(hsv, lower_red2, upper_red2)
    red2_pixels = cv2.countNonZero(mask_red2)

    if red2_pixels > max_pixels:
        dominant_color = "Red"

    return dominant_color
