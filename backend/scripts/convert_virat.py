import glob
import os

import cv2

# VIRAT object type -> COARSE taxonomy ids (backend/ml/taxonomy.py)
# 0: person   1: car
# NOTE: legacy runs wrote Car as 1 then relied on fix_existing_labels.py to bump it.
#       Coarse ids are final here; no second-pass remap.
VIRAT_TO_UNIFIED = {
    "Person": 0,
    "Vehicle": 1,
    "Car": 1,
}


def parse_virat_types(types_file):
    """Parses VIRAT .types.yml to map object IDs to their class type."""
    obj_types = {}
    if not os.path.exists(types_file):
        return obj_types

    with open(types_file) as f:
        for line in f:
            if "types:" in line and "id1:" in line:
                try:
                    # Example line: - { types: { id1: 0 , cset3: { Person: 1.0 } } }
                    id_part = line.split("id1:")[1].split(",")[0].strip()
                    obj_id = int(id_part)

                    if "cset3: {" in line:
                        type_str = line.split("cset3: {")[1].split(":")[0].strip()
                        obj_types[obj_id] = type_str
                except Exception:
                    continue
    return obj_types


def convert_virat(virat_path, output_path, extract_fps=1):
    print(f"Extracting VIRAT dataset from {virat_path} to {output_path}...")

    video_dir = os.path.join(virat_path, "Test Dataset", "videos")
    # For annotations, VIRAT stores them in a similar folder structure or a separate one.
    # We will assume they are alongside the videos or provide a way to find them.
    # The user had them in J:\Data set\viratannotations-master\validate
    anno_dir = r"J:\Data set\viratannotations-master\validate"

    os.makedirs(os.path.join(output_path, "images", "train"), exist_ok=True)
    os.makedirs(os.path.join(output_path, "labels", "train"), exist_ok=True)

    videos = glob.glob(os.path.join(video_dir, "*.mp4"))

    for vid_path in videos:
        vid_name = os.path.basename(vid_path).replace(".mp4", "")
        geom_file = os.path.join(anno_dir, f"{vid_name}.geom.yml")
        types_file = os.path.join(anno_dir, f"{vid_name}.types.yml")

        if not os.path.exists(geom_file) or not os.path.exists(types_file):
            print(f"Skipping {vid_name} - No annotations found.")
            continue

        print(f"Processing Video: {vid_name}")
        obj_types = parse_virat_types(types_file)

        # Parse Geometry: obj_id, duration, frame_id, x, y, w, h
        frame_boxes = {}
        with open(geom_file) as f:
            for line in f:
                if "geom:" in line and "id1:" in line and "ts0:" in line and "g0:" in line:
                    try:
                        # Example: - { geom: { id1: 0, id0: 0, ts0: 421, ts1: 14.03, g0: 1818 693 1876 780 , src: truth ... } }
                        obj_id = int(line.split("id1:")[1].split(",")[0].strip())
                        frame_id = int(line.split("ts0:")[1].split(",")[0].strip())

                        g0_str = line.split("g0:")[1].split(",")[0].strip()
                        x_min, y_min, x_max, y_max = map(float, g0_str.split()[:4])

                        if obj_id not in obj_types:
                            continue
                        v_type = obj_types[obj_id]

                        if v_type not in VIRAT_TO_UNIFIED:
                            continue
                        unified_class = VIRAT_TO_UNIFIED[v_type]

                        if frame_id not in frame_boxes:
                            frame_boxes[frame_id] = []

                        w = x_max - x_min
                        h = y_max - y_min
                        frame_boxes[frame_id].append((unified_class, x_min, y_min, w, h))
                    except Exception:
                        continue

        # Open video and extract frames
        cap = cv2.VideoCapture(vid_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_interval = max(1, int(fps / extract_fps))  # Extract N frames per second

        width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)

        frame_idx = 0
        saved_count = 0

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            # Only save frames that have annotations AND match our extraction interval
            if frame_idx % frame_interval == 0 and frame_idx in frame_boxes:
                img_out = os.path.join(output_path, "images", "train", f"virat_{vid_name}_{frame_idx:06d}.jpg")
                lbl_out = os.path.join(output_path, "labels", "train", f"virat_{vid_name}_{frame_idx:06d}.txt")

                cv2.imwrite(img_out, frame)

                with open(lbl_out, "w") as f:
                    for u_cls, x, y, w, h in frame_boxes[frame_idx]:
                        # YOLO normalization
                        cx = (x + w / 2) / width
                        cy = (y + h / 2) / height
                        nw = w / width
                        nh = h / height
                        f.write(f"{u_cls} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}\n")

                saved_count += 1

            frame_idx += 1

        cap.release()
        print(f"  -> Extracted {saved_count} frames for {vid_name}")

    print("\nVIRAT extraction complete!")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--virat", type=str, default=r"j:\Data set\VIRAT\VIRAT Video Dataset Release 1.0")
    parser.add_argument("--out", type=str, default=r"backend\data\unified_yolo")
    args = parser.parse_args()

    out_abs = os.path.abspath(args.out)
    convert_virat(args.virat, out_abs)
