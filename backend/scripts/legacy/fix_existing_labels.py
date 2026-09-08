import os
import glob
from tqdm import tqdm

def upgrade_labels():
    label_dir = os.path.abspath(r"backend\data\unified_yolo\labels\train")
    if not os.path.exists(label_dir):
        print(f"Error: Label directory not found at {label_dir}")
        return
        
    txt_files = glob.glob(os.path.join(label_dir, "*.txt"))
    print(f"Upgrading {len(txt_files)} label files to the 91-Class Taxonomy in-place...")
    
    modified_count = 0
    
    for txt_path in tqdm(txt_files):
        filename = os.path.basename(txt_path)
        
        with open(txt_path, "r") as f:
            lines = f.readlines()
            
        if not lines: continue
        
        new_lines = []
        modified = False
        
        for line in lines:
            parts = line.strip().split()
            if len(parts) < 5: 
                new_lines.append(line)
                continue
                
            cls_id = int(parts[0])
            new_id = cls_id
            
            if filename.startswith("virat_"):
                # Old VIRAT car was 1. New Car is 2.
                if cls_id == 1: new_id = 2
            
            elif filename.startswith("plate_"):
                # Old plate was 2. New plate is 7.
                if cls_id == 2: new_id = 7
                
            elif filename.startswith("milfield_"):
                # Old mil_field: 3 (Aircraft), 6 (Tank)
                if cls_id == 3: new_id = 9 # Generic Jet
                if cls_id == 6: new_id = 8 # Tank
                
            elif filename.startswith("nightvis_"):
                # Old NV: 7. New NV: 17.
                if cls_id == 7: new_id = 17
                
            if new_id != cls_id:
                parts[0] = str(new_id)
                modified = True
                
            new_lines.append(" ".join(parts) + "\n")
            
        if modified:
            with open(txt_path, "w") as f:
                f.writelines(new_lines)
            modified_count += 1
            
    print(f"\nSuccessfully upgraded {modified_count} files without losing data!")

if __name__ == "__main__":
    upgrade_labels()
