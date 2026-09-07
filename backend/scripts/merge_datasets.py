import os
import shutil
import glob
from tqdm import tqdm

def merge_datasets(mot_path, plate_path, output_path):
    print(f"Creating Unified YOLO Dataset at {output_path}...")
    
    # Create unified structure
    for split in ["train", "valid"]:
        os.makedirs(os.path.join(output_path, "images", split), exist_ok=True)
        os.makedirs(os.path.join(output_path, "labels", split), exist_ok=True)

    # 1. Process MOT17 (Class 0 stays 0)
    # Note: Our script converted MOT17 to a "train" split. We'll put it in unified "train"
    print("Processing MOT17 Dataset...")
    mot_imgs = glob.glob(os.path.join(mot_path, "images", "train", "*.jpg"))
    for img_path in tqdm(mot_imgs):
        filename = os.path.basename(img_path)
        lbl_path = img_path.replace("images", "labels").replace(".jpg", ".txt")
        
        # Output paths
        out_img = os.path.join(output_path, "images", "train", f"mot_{filename}")
        out_lbl = os.path.join(output_path, "labels", "train", f"mot_{filename.replace('.jpg', '.txt')}")
        
        shutil.copy(img_path, out_img)
        if os.path.exists(lbl_path):
            shutil.copy(lbl_path, out_lbl) # Class is already 0

    # 2. Process License Plates (Class 0 becomes 2)
    print("Processing License Plate Dataset...")
    for split in ["train", "valid"]:
        plate_imgs = glob.glob(os.path.join(plate_path, split, "images", "*.jpg"))
        for img_path in tqdm(plate_imgs):
            filename = os.path.basename(img_path)
            lbl_path = img_path.replace("images", "labels").replace(".jpg", ".txt")
            
            out_img = os.path.join(output_path, "images", split, f"plate_{filename}")
            out_lbl = os.path.join(output_path, "labels", split, f"plate_{filename.replace('.jpg', '.txt')}")
            
            shutil.copy(img_path, out_img)
            
            if os.path.exists(lbl_path):
                # Rewrite class 0 to 2
                with open(lbl_path, "r") as f_in, open(out_lbl, "w") as f_out:
                    for line in f_in:
                        parts = line.strip().split()
                        if not parts: continue
                        class_id = int(parts[0])
                        if class_id == 0:
                            parts[0] = "2" # Change Plate to 2
                        f_out.write(" ".join(parts) + "\n")
                        
    print(f"\nSuccessfully created Unified Dataset at {output_path}!")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mot", type=str, default=r"F:\Projects\SIH 26187\backend\backend\data\mot17_yolo")
    parser.add_argument("--plate", type=str, default=r"j:\Data set\License Plate Recognition.v4-resized640_aug3x-accurate.yolov8")
    parser.add_argument("--out", type=str, default=r"backend\data\unified_yolo")
    args = parser.parse_args()
    
    out_abs = os.path.abspath(args.out)
    merge_datasets(args.mot, args.plate, out_abs)
