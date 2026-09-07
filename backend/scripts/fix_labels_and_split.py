"""
Fix all label issues in unified_yolo:
1. Clamp coordinates to [0, 1] (fixes MOT17 out-of-bounds)
2. Strip segmentation polygons (fixes mixed segment/detection)
3. Remove negative coordinates
4. Create a validation split (10% of training data)
5. Delete stale .cache files
"""
import os
import glob
import shutil
import random
from tqdm import tqdm

BASE_DIR = r"F:\Projects\SIH 26187\backend\data\unified_yolo"

def fix_labels(label_dir):
    """Fix all label files in both train and valid."""
    txt_files = glob.glob(os.path.join(label_dir, "*.txt"))
    print(f"Scanning {len(txt_files)} label files for issues...")
    
    fixed_count = 0
    
    for txt_path in tqdm(txt_files, desc="Fixing labels"):
        with open(txt_path, "r") as f:
            lines = f.readlines()
        
        if not lines:
            continue
        
        new_lines = []
        modified = False
        
        for line in lines:
            parts = line.strip().split()
            if len(parts) < 5:
                continue
            
            cls_id = parts[0]
            
            # Only keep the first 5 values (class + 4 bbox coords)
            # This strips any segmentation polygon points
            if len(parts) > 5:
                parts = parts[:5]
                modified = True
            
            # Parse bbox values
            try:
                vals = [float(v) for v in parts[1:5]]
            except ValueError:
                modified = True
                continue
            
            # Check for negative values - skip entire line
            if any(v < 0 for v in vals):
                modified = True
                continue
            
            # Clamp out-of-bounds values to [0.0, 1.0]
            clamped = False
            for i in range(len(vals)):
                if vals[i] > 1.0:
                    vals[i] = 1.0
                    clamped = True
            if clamped:
                modified = True
            
            new_lines.append(f"{cls_id} {vals[0]:.6f} {vals[1]:.6f} {vals[2]:.6f} {vals[3]:.6f}\n")
        
        if modified:
            with open(txt_path, "w") as f:
                f.writelines(new_lines)
            fixed_count += 1
    
    print(f"Fixed {fixed_count} label files.")

def create_val_split(base_dir, val_ratio=0.1):
    """Move 10% of training images+labels into a validation split."""
    train_img_dir = os.path.join(base_dir, "images", "train")
    train_lbl_dir = os.path.join(base_dir, "labels", "train")
    val_img_dir = os.path.join(base_dir, "images", "valid")
    val_lbl_dir = os.path.join(base_dir, "labels", "valid")
    
    os.makedirs(val_img_dir, exist_ok=True)
    os.makedirs(val_lbl_dir, exist_ok=True)
    
    # Check if valid already has images
    existing = glob.glob(os.path.join(val_img_dir, "*.jpg"))
    if len(existing) > 100:
        print(f"Validation set already has {len(existing)} images. Skipping split.")
        return
    
    all_images = glob.glob(os.path.join(train_img_dir, "*.jpg"))
    random.seed(42)
    random.shuffle(all_images)
    
    val_count = int(len(all_images) * val_ratio)
    val_images = all_images[:val_count]
    
    print(f"Moving {val_count} images ({val_ratio*100:.0f}%) from train to validation set...")
    
    for img_path in tqdm(val_images, desc="Creating val split"):
        filename = os.path.basename(img_path)
        lbl_filename = filename.replace(".jpg", ".txt")
        
        lbl_path = os.path.join(train_lbl_dir, lbl_filename)
        
        shutil.move(img_path, os.path.join(val_img_dir, filename))
        if os.path.exists(lbl_path):
            shutil.move(lbl_path, os.path.join(val_lbl_dir, lbl_filename))
    
    print(f"Validation split created: {val_count} images moved.")

def delete_cache(base_dir):
    """Delete stale .cache files so YOLO re-scans the data."""
    for cache_file in glob.glob(os.path.join(base_dir, "**", "*.cache"), recursive=True):
        os.remove(cache_file)
        print(f"Deleted cache: {cache_file}")

if __name__ == "__main__":
    label_dir = os.path.join(BASE_DIR, "labels", "train")
    
    print("=" * 60)
    print("Step 1: Fixing all label issues (train)...")
    print("=" * 60)
    fix_labels(label_dir)
    
    print("\n" + "=" * 60)
    print("Step 2: Creating validation split (10%)...")
    print("=" * 60)
    create_val_split(BASE_DIR)
    
    # Also fix validation labels
    val_label_dir = os.path.join(BASE_DIR, "labels", "valid")
    if os.path.exists(val_label_dir):
        print("\n" + "=" * 60)
        print("Step 3: Fixing validation labels...")
        print("=" * 60)
        fix_labels(val_label_dir)
    
    print("\n" + "=" * 60)
    print("Step 4: Deleting stale cache files...")
    print("=" * 60)
    delete_cache(BASE_DIR)
    
    print("\nAll issues fixed! You can now run the training command.")
