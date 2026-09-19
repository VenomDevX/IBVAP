"""
IBVAP — Coarse detector taxonomy (single source of truth)
=========================================================
The detector is trained on ~13 COARSE classes, not the old 91 fine-grained ones.
The surveillance logic (zones, fence, loitering, risk) only needs coarse categories;
a 6 GB / yolo11s budget cannot separate 73 near-identical jet types anyway.

Imported by:
  * the data-prep scripts   (backend/ml/remap_to_coarse.py, verify_dataset.py, ...)
  * the live pipeline        (src/detection/detector.py, src/tracking/tracker.py)

Fine-grained aircraft type ID (F-16 vs F-18) is Phase 2 — a separate classifier that
runs only on `aircraft` / `helicopter` / `drone_uav` / `military_ground_vehicle` crops.
"""

from __future__ import annotations

# ──────────────────────────────────────────────────────────────
# Coarse classes — ordered; index == YOLO class id in dataset_coarse.yaml
# ──────────────────────────────────────────────────────────────
COARSE_NAMES: list[str] = [
    "person",  # 0
    "car",  # 1
    "bus",  # 2
    "truck",  # 3
    "motorcycle",  # 4
    "bicycle",  # 5
    "license_plate",  # 6
    "military_ground_vehicle",  # 7  (tanks, armour)
    "aircraft",  # 8  (fixed-wing: fighters, bombers, transports, recon, generic jets)
    "helicopter",  # 9
    "drone_uav",  # 10
    "night_vision_object",  # 11 (IR/thermal blobs — legacy catch-all, see A6 in the plan)
    "animal",  # 12
]
COARSE_ID: dict[str, int] = {name: i for i, name in enumerate(COARSE_NAMES)}
NUM_COARSE = len(COARSE_NAMES)

# ──────────────────────────────────────────────────────────────
# Old 91-class taxonomy (matches backend/configs/dataset.yaml and
# scripts/crop_to_folders.py::CLASSES) — used only to remap existing labels.
# ──────────────────────────────────────────────────────────────
FINE_NAMES: dict[int, str] = {
    0: "Person",
    1: "Soldier",
    2: "Car",
    3: "Bus",
    4: "Forklift",
    5: "Motorcycle",
    6: "Bicycle",
    7: "License Plate",
    8: "Tank",
    9: "Generic Jet",
    10: "Large Military Plane",
    11: "Dog",
    12: "Cat",
    13: "Bird",
    14: "Horse",
    15: "Cow",
    16: "Sheep",
    17: "Night Vision Object",
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

# rotary-wing among the 18–90 military types
_HELICOPTERS = {"AH64", "CH47", "Ka27", "Ka52", "Mi24", "Mi28", "UH60", "V22", "Z19"}
# unmanned among the 18–90 military types
_DRONES = {"MQ9", "RQ4", "TB2", "TB001", "WZ7"}


def _fine_to_coarse_id(fine_id: int) -> int:
    """Map one old 91-class id -> a coarse id."""
    name = FINE_NAMES[fine_id]
    explicit = {
        "Person": "person",
        "Soldier": "person",
        "Car": "car",
        "Bus": "bus",
        "Forklift": "truck",
        "Motorcycle": "motorcycle",
        "Bicycle": "bicycle",
        "License Plate": "license_plate",
        "Tank": "military_ground_vehicle",
        "Generic Jet": "aircraft",
        "Large Military Plane": "aircraft",
        "Night Vision Object": "night_vision_object",
        "Dog": "animal",
        "Cat": "animal",
        "Bird": "animal",
        "Horse": "animal",
        "Cow": "animal",
        "Sheep": "animal",
    }
    if name in explicit:
        return COARSE_ID[explicit[name]]
    if name in _HELICOPTERS:
        return COARSE_ID["helicopter"]
    if name in _DRONES:
        return COARSE_ID["drone_uav"]
    return COARSE_ID["aircraft"]  # every other 18–90 fixed-wing type


FINE_TO_COARSE: dict[int, int] = {fid: _fine_to_coarse_id(fid) for fid in FINE_NAMES}

# ──────────────────────────────────────────────────────────────
# Normalisation for the live pipeline
# ──────────────────────────────────────────────────────────────
# Downstream code (pipeline.py ANPR gate, track_manager, detection_result.vehicle_count,
# risk_classifier features, draw colour dicts) keys off a lowercase vocabulary:
#   person / car / bus / truck / motorcycle / bicycle
# The coarse names already match those; the 7 new names pass through unchanged.
# This map exists so a custom-trained model whose names differ in case/spelling
# ("Car", "License_Plate") still lands on the canonical token.
_ALIASES: dict[str, str] = {
    "licenseplate": "license_plate",
    "license-plate": "license_plate",
    "plate": "license_plate",
    "militarygroundvehicle": "military_ground_vehicle",
    "tank": "military_ground_vehicle",
    "armored_vehicle": "military_ground_vehicle",
    "armoured_vehicle": "military_ground_vehicle",
    "jet": "aircraft",
    "airplane": "aircraft",
    "plane": "aircraft",
    "fixed_wing": "aircraft",
    "heli": "helicopter",
    "rotary_wing": "helicopter",
    "drone": "drone_uav",
    "uav": "drone_uav",
    "uas": "drone_uav",
    "nightvisionobject": "night_vision_object",
    "night_vision": "night_vision_object",
    "ir_object": "night_vision_object",
    "van": "truck",
    "lorry": "truck",
    "pickup": "truck",
    "bike": "bicycle",
    "cycle": "bicycle",
    "motorbike": "motorcycle",
    "scooter": "motorcycle",
    "pedestrian": "person",
    "people": "person",
    "soldier": "person",
}


def normalize(name: str) -> str:
    """Canonicalise a raw model class name to the pipeline vocabulary.

    'Car' -> 'car', 'License_Plate' -> 'license_plate', 'AH64' -> unknown -> passthrough lowered.
    """
    if not name:
        return "unknown"
    key = name.strip().lower().replace(" ", "_")
    if key in COARSE_ID:
        return key
    flat = key.replace("_", "").replace("-", "")
    if flat in _ALIASES:
        return _ALIASES[flat]
    if key in _ALIASES:
        return _ALIASES[key]
    return key


NORMALIZE: dict[str, str] = {n: n for n in COARSE_NAMES}
NORMALIZE.update(_ALIASES)

# convenience groups
VEHICLE_TYPES = {"car", "bus", "truck", "motorcycle", "bicycle", "night_vision_object"}
MILITARY_TYPES = {"military_ground_vehicle", "aircraft", "helicopter", "drone_uav"}
# night_vision_object included: a car/truck seen at night is often stuck on
# this catch-all class, but a plate is still worth attempting on the crop.
ANPR_TYPES = {"car", "bus", "truck", "motorcycle", "night_vision_object"}  # crops worth OCR-ing


def write_yaml(path: str, dataset_path: str, train: str, val: str) -> None:
    """Emit a YOLO data.yaml with the coarse `names:` block."""

    lines = [
        "# Coarse detector taxonomy — generated by backend/ml/taxonomy.py",
        f"# {NUM_COARSE} classes. Fine-grained military type ID is Phase 2 (separate classifier).",
        "",
        f"path: {dataset_path}",
        f"train: {train}",
        f"val: {val}",
        "",
        f"nc: {NUM_COARSE}",
        "names:",
    ]
    for i, name in enumerate(COARSE_NAMES):
        lines.append(f"  {i}: {name}")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":  # quick self-check
    from collections import Counter

    dist = Counter(FINE_TO_COARSE.values())
    print(f"{NUM_COARSE} coarse classes:")
    for i, n in enumerate(COARSE_NAMES):
        fine = [FINE_NAMES[f] for f, c in FINE_TO_COARSE.items() if c == i]
        print(f"  {i:2d} {n:24s}  <- {len(fine):2d} fine classes")
    assert all(0 <= c < NUM_COARSE for c in FINE_TO_COARSE.values())
    assert normalize("Car") == "car"
    assert normalize("License_Plate") == "license_plate"
    assert normalize("Tank") == "military_ground_vehicle"
    print("OK")
