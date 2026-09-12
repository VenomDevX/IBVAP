import os
import shutil

from tqdm import tqdm


def convert_mot17_to_yolo(mot_path, output_path):
    print(f"Converting MOT17 dataset from {mot_path} to YOLO format at {output_path}...")

    img_out = os.path.join(output_path, "images", "train")
    lbl_out = os.path.join(output_path, "labels", "train")

    os.makedirs(img_out, exist_ok=True)
    os.makedirs(lbl_out, exist_ok=True)

    seqs = [s for s in os.listdir(mot_path) if os.path.isdir(os.path.join(mot_path, s))]

    for seq in seqs:
        print(f"Processing sequence: {seq}")
        seq_path = os.path.join(mot_path, seq)
        img_dir = os.path.join(seq_path, "img1")
        gt_file = os.path.join(seq_path, "gt", "gt.txt")

        if not os.path.exists(gt_file):
            print(f"Skipping {seq} - No ground truth found.")
            continue

        # Parse ground truth
        # MOT format: frame, id, bb_left, bb_top, bb_width, bb_height, conf, class, vis
        frame_annotations = {}
        with open(gt_file) as f:
            for line in f:
                parts = line.strip().split(",")
                if len(parts) < 9:
                    continue
                frame = int(parts[0])
                class_id = int(parts[7])
                vis = float(parts[8])

                # Class 1 in MOT17 is Pedestrian. We map it to class 0 for YOLO.
                if class_id != 1 or vis < 0.2:
                    continue

                x, y, w, h = map(float, parts[2:6])

                if frame not in frame_annotations:
                    frame_annotations[frame] = []
                frame_annotations[frame].append((x, y, w, h))

        # Read seqinfo.ini to get image dimensions
        seqinfo = os.path.join(seq_path, "seqinfo.ini")
        img_width, img_height = 1920, 1080  # Default fallback
        if os.path.exists(seqinfo):
            with open(seqinfo) as f:
                for line in f:
                    if line.startswith("imWidth="):
                        img_width = int(line.split("=")[1])
                    elif line.startswith("imHeight="):
                        img_height = int(line.split("=")[1])

        # Copy images and write labels
        frames = sorted(frame_annotations.keys())
        for frame in tqdm(frames):
            img_name = f"{frame:06d}.jpg"
            src_img = os.path.join(img_dir, img_name)

            if not os.path.exists(src_img):
                continue

            new_name = f"{seq}_{frame:06d}"
            dst_img = os.path.join(img_out, f"{new_name}.jpg")
            dst_lbl = os.path.join(lbl_out, f"{new_name}.txt")

            # Copy image
            shutil.copy(src_img, dst_img)

            # Write YOLO label
            with open(dst_lbl, "w") as f:
                for x, y, w, h in frame_annotations[frame]:
                    # Normalize for YOLO (x_center, y_center, w, h)
                    x_center = (x + w / 2.0) / img_width
                    y_center = (y + h / 2.0) / img_height
                    w_norm = w / img_width
                    h_norm = h / img_height
                    f.write(f"0 {x_center:.6f} {y_center:.6f} {w_norm:.6f} {h_norm:.6f}\n")

    print("\nConversion Complete! Dataset is ready for YOLO training.")
    print(f"Update your dataset.yaml to point to: {output_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mot-path", type=str, default=r"J:\Data set\MOT17\MOT17\train", help="Path to MOT17 train folder"
    )
    parser.add_argument("--output", type=str, default=r"backend\data\mot17_yolo", help="Output path for YOLO dataset")
    args = parser.parse_args()

    # Needs to be absolute or relative to where script is run
    output_abs = os.path.abspath(args.output)
    convert_mot17_to_yolo(args.mot_path, output_abs)
