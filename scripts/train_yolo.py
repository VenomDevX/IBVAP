"""
IBVAP — Custom YOLOv8 Training Script
Use this script to train your own object detection model using a custom dataset.

Prerequisites:
1. Your dataset must be formatted in YOLO format (images in one folder, .txt labels in another).
2. You need a data.yaml file that defines your dataset paths and classes.

Example dataset structure:
dataset/
├── data.yaml
├── images/
│   ├── train/
│   └── val/
└── labels/
    ├── train/
    └── val/

Usage:
    python train_yolo.py --data path/to/data.yaml --epochs 50 --batch 16
"""

import argparse
from ultralytics import YOLO

def main():
    parser = argparse.ArgumentParser(description="Train a custom YOLOv8 model for IBVAP")
    parser.add_argument("--data", type=str, required=True, help="Path to the dataset data.yaml file")
    parser.add_argument("--epochs", type=int, default=50, help="Number of training epochs")
    parser.add_argument("--batch", type=int, default=16, help="Batch size (reduce if you run out of GPU memory)")
    parser.add_argument("--imgsz", type=int, default=640, help="Image size for training")
    parser.add_argument("--weights", type=str, default="yolov8n.pt", help="Pre-trained weights to start from (yolov8n.pt, yolov8s.pt, etc.)")
    parser.add_argument("--name", type=str, default="ibvap_custom_model", help="Name of the experiment/run")
    
    args = parser.parse_args()

    print(f"--- Starting YOLOv8 Training ---")
    print(f"Dataset: {args.data}")
    print(f"Epochs: {args.epochs}")
    print(f"Batch Size: {args.batch}")
    print(f"Image Size: {args.imgsz}")
    print(f"Base Model: {args.weights}")
    
    # Load a pretrained model (recommended for transfer learning)
    model = YOLO(args.weights)
    
    # Train the model
    results = model.train(
        data=args.data,
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        name=args.name,
        device="0" # Use 'cpu' if you don't have an NVIDIA GPU, or '0' for first GPU
    )
    
    print("\n--- Training Complete ---")
    print(f"Your custom weights are saved in: runs/detect/{args.name}/weights/best.pt")
    print("To use this model in IBVAP, update your configuration to point to this path.")

if __name__ == "__main__":
    main()
