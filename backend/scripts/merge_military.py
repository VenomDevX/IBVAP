import os
import shutil
import glob
from tqdm import tqdm

# Master Classes
# 0: Person
# 1: Car
# 2: License Plate
# 3: Military Aircraft
# 4: Two-Wheeler
# 5: Animal
# 6: Tank / Armored Vehicle
# 7: Night Vision Object

def process_dataset(dataset_path, output_path, mapping_dict, prefix):
    print(f"Processing military dataset from {dataset_path} ...")
    
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
            
            shutil.copy(img_path, out_img)
            
            if os.path.exists(lbl_path):
                has_valid_boxes = False
                with open(lbl_path, "r") as f_in, open(out_lbl, "w") as f_out:
                    for line in f_in:
                        parts = line.strip().split()
                        if not parts: continue
                        class_id = int(parts[0])
                        
                        if class_id in mapping_dict:
                            unified_id = mapping_dict[class_id]
                            parts[0] = str(unified_id)
                            f_out.write(" ".join(parts) + "\n")
                            has_valid_boxes = True
                            
                if not has_valid_boxes:
                    open(out_lbl, 'w').close()

if __name__ == "__main__":
    output_abs = os.path.abspath(r"backend\data\unified_yolo")
    
    # 1. Military Dataset 3 ('person', 'soldier') -> 0: Person
    mil_3_path = r"j:\Data set\Military Dataset 3.yolov8"
    if os.path.exists(mil_3_path):
        process_dataset(mil_3_path, output_abs, {0: 0, 1: 0}, "mil3")
        
    # 2. Military field object detection ('jet', 'land', 'large_mil_plane', 'tanks')
    mil_field_path = r"j:\Data set\Militry field object detection.yolov8 (1)"
    if os.path.exists(mil_field_path):
        # 0:jet->3, 2:plane->3, 3:tanks->6
        process_dataset(mil_field_path, output_abs, {0: 3, 2: 3, 3: 6}, "milfield")
        
    # 3. Night Vision (0-11) -> 7: Night Vision Object
    nv_path = r"j:\Data set\night-vision.v3i.yolov8"
    if os.path.exists(nv_path):
        nv_mapping = {i: 7 for i in range(12)}
        process_dataset(nv_path, output_abs, nv_mapping, "nightvis")
        
    # 4. Thermal Camera ('glasses', 'hat', 'head', 'mask') -> 0: Person
    thermal_path = r"j:\Data set\thermal camera detection.v3i.yolov8"
    if os.path.exists(thermal_path):
        therm_mapping = {0: 0, 1: 0, 2: 0, 3: 0}
        process_dataset(thermal_path, output_abs, therm_mapping, "thermal")
        
    print("\nAll Military Datasets Successfully Merged into unified_yolo!")
