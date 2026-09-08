import os
import shutil
import glob
from tqdm import tqdm

# Unified Classes
# 0: Person
# 1: Car
# 2: License Plate
# 3: Military Aircraft
# 4: Two-Wheeler
# 5: Animal

# Mappings for "People Detection.v12i.yolov8"
PEOPLE_TO_UNIFIED = {
    idx: 0 for idx in [0, 1, 2, 7, 8, 9, 10, 15, 29, 32, 36, 41, 42, 43] # Person
}
PEOPLE_TO_UNIFIED.update({idx: 1 for idx in [5, 20, 21, 30]}) # Car
PEOPLE_TO_UNIFIED.update({idx: 3 for idx in [13]}) # Aircraft
PEOPLE_TO_UNIFIED.update({idx: 4 for idx in [3, 4, 6, 16, 25, 40]}) # Two-wheeler
PEOPLE_TO_UNIFIED.update({idx: 5 for idx in [17, 22, 24, 28, 35, 46]}) # Animal

def process_dataset(dataset_path, output_path, mapping_dict, prefix, default_class=None):
    print(f"Processing dataset from {dataset_path} ...")
    
    for split in ["train", "valid"]:
        img_dir = os.path.join(dataset_path, split, "images")
        if not os.path.exists(img_dir):
            continue
            
        imgs = glob.glob(os.path.join(img_dir, "*.jpg"))
        for img_path in tqdm(imgs, desc=f"Copying {split}"):
            filename = os.path.basename(img_path)
            lbl_path = img_path.replace("images", "labels").replace(".jpg", ".txt")
            
            out_img = os.path.join(output_path, "images", "train", f"{prefix}_{filename}")
            out_lbl = os.path.join(output_path, "labels", "train", f"{prefix}_{filename.replace('.jpg', '.txt')}")
            
            # Copy Image
            shutil.copy(img_path, out_img)
            
            # Rewrite Labels
            if os.path.exists(lbl_path):
                has_valid_boxes = False
                with open(lbl_path, "r") as f_in, open(out_lbl, "w") as f_out:
                    for line in f_in:
                        parts = line.strip().split()
                        if not parts: continue
                        class_id = int(parts[0])
                        
                        unified_id = None
                        if default_class is not None:
                            unified_id = default_class
                        elif class_id in mapping_dict:
                            unified_id = mapping_dict[class_id]
                            
                        if unified_id is not None:
                            parts[0] = str(unified_id)
                            f_out.write(" ".join(parts) + "\n")
                            has_valid_boxes = True
                
                # If we ignored all boxes (e.g. it was just a picture of a TV), we can keep the image as a negative sample 
                # (YOLO handles images without txt files or empty txt files as background)
                if not has_valid_boxes:
                    # Clear the file so it's empty
                    open(out_lbl, 'w').close()

if __name__ == "__main__":
    output_abs = os.path.abspath(r"backend\data\unified_yolo")
    
    # 1. Border Defence (All classes become 3: Military Aircraft)
    border_path = r"j:\Data set\Border Defence.v1i.yolov8"
    if os.path.exists(border_path):
        process_dataset(border_path, output_abs, {}, "border", default_class=3)
    
    # 2. People Detection
    people_path = r"j:\Data set\People Detection.v12i.yolov8"
    if os.path.exists(people_path):
        process_dataset(people_path, output_abs, PEOPLE_TO_UNIFIED, "people_det", default_class=None)
        
    print("\nExternal Datasets Successfully Added to Unified YOLO!")
