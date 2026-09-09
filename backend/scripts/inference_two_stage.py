"""
Two-Stage Inference Pipeline for IBVAP
======================================
Stage 1: YOLO detects objects → bounding boxes
Stage 2: ResNet classifies each crop → fine-grained class

Usage:
    python scripts/inference_two_stage.py --image path/to/image.jpg
    python scripts/inference_two_stage.py --video path/to/video.mp4
"""

import argparse
import json
import cv2
import torch
from torchvision import models, transforms
from ultralytics import YOLO


class TwoStageDetector:
    """
    YOLO (detection) + ResNet (classification) two-stage pipeline.
    """
    
    def __init__(self, yolo_weights, resnet_weights, class_mapping_path, device="cuda:0"):
        self.device = torch.device(device if torch.cuda.is_available() else "cpu")
        
        # Load YOLO
        print(f"Loading YOLO from: {yolo_weights}")
        self.yolo = YOLO(yolo_weights)
        
        # Load class mapping
        with open(class_mapping_path, "r") as f:
            self.idx_to_class = json.load(f)
        self.num_classes = len(self.idx_to_class)
        print(f"Loaded {self.num_classes} class labels")
        
        # Load ResNet
        print(f"Loading ResNet from: {resnet_weights}")
        checkpoint = torch.load(resnet_weights, map_location=self.device)
        
        self.resnet = models.resnet50()
        in_features = self.resnet.fc.in_features
        self.resnet.fc = torch.nn.Sequential(
            torch.nn.Dropout(0.3),
            torch.nn.Linear(in_features, 512),
            torch.nn.ReLU(),
            torch.nn.Dropout(0.2),
            torch.nn.Linear(512, self.num_classes)
        )
        self.resnet.load_state_dict(checkpoint['model_state_dict'])
        self.resnet.to(self.device)
        self.resnet.eval()
        
        # ResNet preprocessing
        self.transform = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                 std=[0.229, 0.224, 0.225]),
        ])
        
        print("Two-stage detector ready!")
    
    def classify_crop(self, crop_bgr):
        """Run ResNet on a single crop to get fine-grained class."""
        crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        tensor = self.transform(crop_rgb).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            output = self.resnet(tensor)
            probs = torch.softmax(output, dim=1)
            confidence, pred_idx = probs.max(1)
        
        class_name = self.idx_to_class[str(pred_idx.item())]
        return class_name, confidence.item()
    
    def detect(self, frame, conf_threshold=0.25, refine_threshold=0.5):
        """
        Two-stage detection on a single frame.
        
        Returns list of detections:
            [{'bbox': [x1,y1,x2,y2], 'yolo_class': str, 'refined_class': str, 
              'yolo_conf': float, 'resnet_conf': float}]
        """
        # Stage 1: YOLO detection
        results = self.yolo(frame, conf=conf_threshold, verbose=False)
        
        detections = []
        if results and len(results[0].boxes) > 0:
            boxes = results[0].boxes
            
            for i in range(len(boxes)):
                x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy().astype(int)
                yolo_conf = boxes.conf[i].item()
                yolo_cls_id = int(boxes.cls[i].item())
                yolo_cls_name = results[0].names[yolo_cls_id]
                
                # Stage 2: Crop and classify with ResNet
                crop = frame[max(0, y1):y2, max(0, x1):x2]
                if crop.size > 0 and crop.shape[0] > 10 and crop.shape[1] > 10:
                    refined_class, resnet_conf = self.classify_crop(crop)
                    
                    # Use ResNet class only if confident enough
                    if resnet_conf >= refine_threshold:
                        final_class = refined_class
                    else:
                        final_class = yolo_cls_name
                else:
                    refined_class = yolo_cls_name
                    resnet_conf = 0.0
                    final_class = yolo_cls_name
                
                detections.append({
                    'bbox': [int(x1), int(y1), int(x2), int(y2)],
                    'yolo_class': yolo_cls_name,
                    'refined_class': refined_class,
                    'final_class': final_class,
                    'yolo_conf': round(yolo_conf, 3),
                    'resnet_conf': round(resnet_conf, 3),
                })
        
        return detections
    
    def draw_detections(self, frame, detections):
        """Draw bounding boxes with labels on frame."""
        for det in detections:
            x1, y1, x2, y2 = det['bbox']
            label = f"{det['final_class']} ({det['resnet_conf']:.0%})"
            
            # Color based on confidence
            conf = det['resnet_conf']
            if conf > 0.8:
                color = (0, 255, 0)    # Green = high confidence
            elif conf > 0.5:
                color = (0, 255, 255)  # Yellow = medium
            else:
                color = (0, 0, 255)    # Red = low (using YOLO class)
            
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            
            # Label background
            (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(frame, (x1, y1 - h - 8), (x1 + w, y1), color, -1)
            cv2.putText(frame, label, (x1, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        
        return frame


def main():
    parser = argparse.ArgumentParser(description="Two-Stage YOLO+ResNet Inference")
    parser.add_argument("--image", type=str, help="Path to image")
    parser.add_argument("--video", type=str, help="Path to video")
    parser.add_argument("--yolo", type=str,
                        default="runs/detect/outputs/training/ibvap_custom_model/weights/best.pt",
                        help="YOLO weights path")
    parser.add_argument("--resnet", type=str,
                        default="outputs/classifier/best.pt",
                        help="ResNet weights path")
    parser.add_argument("--mapping", type=str,
                        default="outputs/classifier/class_mapping.json",
                        help="Class mapping JSON path")
    parser.add_argument("--conf", type=float, default=0.25, help="YOLO confidence threshold")
    
    args = parser.parse_args()
    
    detector = TwoStageDetector(
        yolo_weights=args.yolo,
        resnet_weights=args.resnet,
        class_mapping_path=args.mapping
    )
    
    if args.image:
        frame = cv2.imread(args.image)
        detections = detector.detect(frame, conf_threshold=args.conf)
        
        print(f"\nFound {len(detections)} objects:")
        for det in detections:
            print(f"  {det['final_class']:20s} | YOLO: {det['yolo_class']} ({det['yolo_conf']:.0%}) "
                  f"| ResNet: {det['refined_class']} ({det['resnet_conf']:.0%})")
        
        frame = detector.draw_detections(frame, detections)
        out_path = "outputs/two_stage_result.jpg"
        cv2.imwrite(out_path, frame)
        print(f"\nResult saved to {out_path}")
    
    elif args.video:
        cap = cv2.VideoCapture(args.video)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        
        out_path = "outputs/two_stage_result.mp4"
        writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (w, h))
        
        frame_count = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            detections = detector.detect(frame, conf_threshold=args.conf)
            frame = detector.draw_detections(frame, detections)
            writer.write(frame)
            
            frame_count += 1
            if frame_count % 30 == 0:
                print(f"Processed {frame_count} frames, {len(detections)} detections")
        
        cap.release()
        writer.release()
        print(f"\nResult saved to {out_path}")


if __name__ == "__main__":
    main()
