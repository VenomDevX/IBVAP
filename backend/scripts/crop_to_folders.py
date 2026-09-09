import glob
import os

import cv2
from tqdm import tqdm

# Granular 91-Class Taxonomy
CLASSES = {
    0: "Person",
    1: "Soldier",
    2: "Car",
    3: "Bus",
    4: "Forklift",
    5: "Motorcycle",
    6: "Bicycle",
    7: "License_Plate",
    8: "Tank",
    9: "Generic_Jet",
    10: "Large_Military_Plane",
    11: "Dog",
    12: "Cat",
    13: "Bird",
    14: "Horse",
    15: "Cow",
    16: "Sheep",
    17: "Night_Vision_Object",
    18: "A10",
    19: "A400M",
    20: "AG600",
    21: "AH64",
    22: "AV8B",
    23: "An124",
    24: "An22",
    25: "An225",
    26: "An72",
    27: "B1",
    28: "B2",
    29: "B21",
    30: "B52",
    31: "Be200",
    32: "C130",
    33: "C17",
    34: "C2",
    35: "C390",
    36: "C5",
    37: "CH47",
    38: "CL415",
    39: "E2",
    40: "E7",
    41: "EF2000",
    42: "F117",
    43: "F14",
    44: "F15",
    45: "F16",
    46: "F18",
    47: "F22",
    48: "F35",
    49: "F4",
    50: "H6",
    51: "J10",
    52: "J20",
    53: "JAS39",
    54: "JF17",
    55: "JH7",
    56: "KC135",
    57: "KF21",
    58: "KJ600",
    59: "Ka27",
    60: "Ka52",
    61: "MQ9",
    62: "Mi24",
    63: "Mi28",
    64: "Mig29",
    65: "Mig31",
    66: "Mirage2000",
    67: "P3",
    68: "RQ4",
    69: "Rafale",
    70: "SR71",
    71: "Su24",
    72: "Su25",
    73: "Su34",
    74: "Su57",
    75: "TB001",
    76: "TB2",
    77: "Tornado",
    78: "Tu160",
    79: "Tu22M",
    80: "Tu95",
    81: "U2",
    82: "UH60",
    83: "US2",
    84: "V22",
    85: "Vulcan",
    86: "WZ7",
    87: "XB70",
    88: "Y20",
    89: "YF23",
    90: "Z19",
}


def extract_crops():
    base_dir = os.path.abspath(r"backend\data\unified_yolo")
    out_dir = os.path.abspath(r"backend\data\cropped_classes")

    # Create class folders
    for cls_name in CLASSES.values():
        os.makedirs(os.path.join(out_dir, cls_name), exist_ok=True)

    img_dir = os.path.join(base_dir, "images", "train")
    if not os.path.exists(img_dir):
        print(f"Error: Unified dataset not found at {img_dir}. Please run the merge scripts first!")
        return

    images = glob.glob(os.path.join(img_dir, "*.jpg"))
    print(f"Extracting object crops from {len(images)} images into 91 Granular Folders...")

    crop_counts = {c: 0 for c in CLASSES.values()}

    for img_path in tqdm(images):
        lbl_path = img_path.replace("images", "labels").replace(".jpg", ".txt")
        if not os.path.exists(lbl_path):
            continue

        with open(lbl_path) as f:
            lines = f.readlines()

        if not lines:
            continue

        # Only read the image if it has labels
        img = cv2.imread(img_path)
        if img is None:
            continue

        h, w = img.shape[:2]
        filename = os.path.basename(img_path).replace(".jpg", "")

        for i, line in enumerate(lines):
            parts = line.strip().split()
            if len(parts) < 5:
                continue

            cls_id = int(parts[0])
            if cls_id not in CLASSES:
                continue

            cls_name = CLASSES[cls_id]
            cx, cy, bw, bh = map(float, parts[1:5])

            # Convert YOLO to pixel coordinates
            x1 = int((cx - bw / 2) * w)
            y1 = int((cy - bh / 2) * h)
            x2 = int((cx + bw / 2) * w)
            y2 = int((cy + bh / 2) * h)

            # Ensure within bounds
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)

            if x2 <= x1 or y2 <= y1:
                continue

            # Crop
            crop = img[y1:y2, x1:x2]

            # Save
            crop_path = os.path.join(out_dir, cls_name, f"{filename}_crop{i}.jpg")
            cv2.imwrite(crop_path, crop)
            crop_counts[cls_name] += 1

    print("\nExtraction Complete! Summary:")
    for cls_name, count in crop_counts.items():
        if count > 0:
            print(f"  - {cls_name}: {count} images")


if __name__ == "__main__":
    extract_crops()
