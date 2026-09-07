import os
import argparse
try:
    from roboflow import Roboflow
except ImportError:
    print("Roboflow package not found. Please install it using: pip install roboflow")
    exit(1)

def download_dataset(api_key):
    """
    Downloads a public License Plate detection dataset from Roboflow in YOLOv8 format.
    """
    rf = Roboflow(api_key=api_key)
    
    print("Connecting to Roboflow and fetching the License Plate dataset...")
    
    # Using a common public license plate dataset on Roboflow Universe
    # Workspace: my-workspace (replace with actual public workspace if known, 
    # but 'roboflow-universe-projects' is a good start)
    # We will use the popular "License Plate Recognition" dataset.
    project = rf.workspace("roboflow-universe-projects").project("license-plate-recognition-rxg4e")
    
    # Download the dataset in yolov8 format to the backend/data/plates directory
    output_path = os.path.join(os.path.dirname(__file__), "..", "data", "plates")
    os.makedirs(output_path, exist_ok=True)
    
    print(f"Downloading dataset to {os.path.abspath(output_path)} ...")
    dataset = project.version(4).download("yolov8", location=output_path)
    
    print(f"\nSuccess! Dataset downloaded and arranged perfectly for YOLOv8 training at: {output_path}")
    print("You can now run the training script!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download License Plate Dataset")
    parser.add_argument("--api-key", type=str, required=True, help="Your Roboflow API Key (get it free from app.roboflow.com)")
    
    args = parser.parse_args()
    download_dataset(args.api_key)
