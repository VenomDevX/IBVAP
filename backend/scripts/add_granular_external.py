import os
import shutil
import glob
from tqdm import tqdm

# Granular Taxonomy Mapping (91 Classes)
# 0: Person
# 1: Soldier
# 2: Car
# 3: Bus
# 4: Forklift/Truck
# 5: Motorcycle
# 6: Bicycle
# 7: License Plate
# 8: Tank
# 9: Generic Jet
# 10: Large Military Plane
# 11: Dog
# 12: Cat
# 13: Bird
# 14: Horse
# 15: Cow
# 16: Sheep
# 17: Night Vision Object
# 18-90: Border Defence specific aircraft

PEOPLE_DET_MAPPING = {
    # Person (0)
    0: 0, 1: 0, 2: 0, 7: 0, 8: 0, 9: 0, 10: 0, 15: 0, 29: 0, 32: 0, 36: 0, 41: 0, 42: 0, 43: 0,
    # Car (2)
    5: 2, 21: 2,
    # Bus (3)
    20: 3,
    # Forklift (4)
    30: 4,
    # Motorcycle (5)
    4: 5, 40: 5,
    # Bicycle (6)
    3: 6, 6: 6, 16: 6, 25: 6,
    # Airplane (9) -> Generic Jet
    13: 9,
    # Animals (11-16)
    28: 11, # dog
    22: 12, # cat
    17: 13, # bird
    35: 14, # horse
    24: 15, # cow
    46: 16  # sheep
}

def process_dataset(dataset_path, output_path, mapping_dict, prefix, offset=0):
    print(f"Processing granular dataset from {dataset_path} ...")
    
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
                        
                        unified_id = None
                        if mapping_dict is not None and class_id in mapping_dict:
                            unified_id = mapping_dict[class_id]
                        elif mapping_dict is None:
                            unified_id = class_id + offset
                            
                        if unified_id is not None:
                            parts[0] = str(unified_id)
                            f_out.write(" ".join(parts) + "\n")
                            has_valid_boxes = True
                            
                if not has_valid_boxes:
                    open(out_lbl, 'w').close()

if __name__ == "__main__":
    output_abs = os.path.abspath(r"backend\data\unified_yolo")
    
    # 1. Border Defence (All 73 classes map to 18 -> 90)
    border_path = r"j:\Data set\Border Defence.v1i.yolov8"
    if os.path.exists(border_path):
        process_dataset(border_path, output_abs, None, "border", offset=18)
    
    # 2. People Detection
    people_path = r"j:\Data set\People Detection.v12i.yolov8"
    if os.path.exists(people_path):
        process_dataset(people_path, output_abs, PEOPLE_DET_MAPPING, "people_det")
        
    print("\nExternal Datasets Successfully Added to Granular 91-Class Dataset!")
