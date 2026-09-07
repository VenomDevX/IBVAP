import argparse
import os

# Fix cuDNN stream mismatch error on RTX 40-series
os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"

from ultralytics import YOLO

def train_model(data_yaml, epochs=100, imgsz=480, batch=2, model_name="yolov8n.pt", resume=False):
    """
    Train a YOLOv8 model for custom object detection.
    Supports resuming from a checkpoint with --resume flag.
    """
    data_yaml = os.path.abspath(data_yaml)
    model_name = os.path.abspath(model_name) if os.path.exists(model_name) else model_name

    print(f"Loading YOLO model: {model_name}")
    model = YOLO(model_name)

    if resume:
        print(f"RESUMING training from checkpoint: {model_name}")
        # When resuming, YOLO reads all settings from the checkpoint
        results = model.train(resume=True)
    else:
        print(f"Starting NEW training using dataset config: {data_yaml}")
        print(f"Epochs: {epochs} | Image Size: {imgsz} | Batch: {batch}")
        results = model.train(
            data=data_yaml,
            epochs=epochs,
            imgsz=imgsz,
            batch=batch,
            device=0,
            workers=2,
            deterministic=False,  # Fix cuDNN STREAM_MISMATCH error
            project="outputs/training",
            name="ibvap_custom_model",
            exist_ok=True
        )

    print("Training complete!")
    print("Best weights: outputs/training/ibvap_custom_model/weights/best.pt")
    print("Last weights: outputs/training/ibvap_custom_model/weights/last.pt")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train YOLOv8 for IBVAP")
    parser.add_argument("--data", type=str, default="configs/dataset.yaml", help="Path to data.yaml")
    parser.add_argument("--epochs", type=int, default=100, help="Number of training epochs")
    parser.add_argument("--batch", type=int, default=2, help="Batch size (2 for 6GB VRAM)")
    parser.add_argument("--imgsz", type=int, default=480, help="Image size (480 for 6GB VRAM)")
    parser.add_argument("--model", type=str, default="yolov8n.pt", help="Pretrained model or checkpoint path")
    parser.add_argument("--resume", action="store_true", help="Resume training from last.pt checkpoint")

    args = parser.parse_args()

    if args.resume:
        # For resume, model must be the last.pt checkpoint
        last_pt = os.path.abspath(args.model)
        if not os.path.exists(last_pt):
            print(f"Error: Checkpoint not found at {last_pt}")
            exit(1)
        train_model(args.data, model_name=last_pt, resume=True)
    else:
        data_path = os.path.abspath(args.data)
        if not os.path.exists(data_path):
            print(f"Error: Dataset config not found at {data_path}")
            exit(1)
        train_model(data_path, args.epochs, args.imgsz, args.batch, args.model)
