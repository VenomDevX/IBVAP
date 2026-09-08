"""
ResNet-50 Image Classifier for IBVAP Two-Stage Pipeline
=======================================================
Stage 1: YOLO detects objects and crops them
Stage 2: This ResNet classifier identifies the exact class from the crop

Uses cropped_classes folder with hierarchical structure.
Handles massive class imbalance with weighted sampling and class capping.
"""

import argparse
import os
import json
import random
import shutil
from pathlib import Path
from collections import Counter

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, WeightedRandomSampler
from torchvision import models, transforms, datasets
from tqdm import tqdm


# ──────────────────────────────────────────────────────────────
# 1. Dataset Preparation
# ──────────────────────────────────────────────────────────────

def prepare_dataset(src_dir, dst_dir, val_ratio=0.2, max_per_class=5000, seed=42):
    """
    Flatten hierarchical cropped_classes into a flat train/val structure.
    Caps images per class to avoid Person (396K) dominating everything.
    
    Output structure:
        dst_dir/
            train/
                A10/
                B2/
                Person/
                ...
            val/
                A10/
                B2/
                Person/
                ...
    """
    random.seed(seed)
    src = Path(src_dir)
    dst = Path(dst_dir)
    
    if (dst / "train").exists() and len(list((dst / "train").iterdir())) > 5:
        print(f"Dataset already prepared at {dst}. Skipping.")
        # Count classes
        classes = sorted([d.name for d in (dst / "train").iterdir() if d.is_dir()])
        print(f"Found {len(classes)} classes in existing dataset.")
        return classes
    
    print("Preparing flat classification dataset...")
    
    # Find all leaf folders with images
    class_folders = {}
    img_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}
    
    for root, dirs, files in os.walk(src):
        images = [f for f in files if Path(f).suffix.lower() in img_exts]
        if images:
            # Use the folder name as class name
            class_name = Path(root).name
            
            # Skip parent folders if their children have subclasses
            # (e.g., skip "Animal" if "Animals/Bird" exists)
            if class_name in ('Animal', 'Military_Aircraft', 'Two_Wheeler'):
                print(f"  Skipping aggregate folder: {class_name}")
                continue
            
            if class_name not in class_folders:
                class_folders[class_name] = []
            class_folders[class_name].extend([os.path.join(root, f) for f in images])
    
    print(f"\nFound {len(class_folders)} classes:")
    for cls, imgs in sorted(class_folders.items(), key=lambda x: -len(x[1])):
        capped = min(len(imgs), max_per_class)
        print(f"  {cls:25s}: {len(imgs):>6d} images (using {capped})")
    
    # Create train/val splits
    for cls, all_images in tqdm(class_folders.items(), desc="Creating splits"):
        # Cap images per class
        if len(all_images) > max_per_class:
            random.shuffle(all_images)
            all_images = all_images[:max_per_class]
        
        random.shuffle(all_images)
        val_count = max(1, int(len(all_images) * val_ratio))
        val_images = all_images[:val_count]
        train_images = all_images[val_count:]
        
        # Copy to train
        train_cls_dir = dst / "train" / cls
        train_cls_dir.mkdir(parents=True, exist_ok=True)
        for img_path in train_images:
            dst_path = train_cls_dir / Path(img_path).name
            if not dst_path.exists():
                shutil.copy2(img_path, dst_path)
        
        # Copy to val
        val_cls_dir = dst / "val" / cls
        val_cls_dir.mkdir(parents=True, exist_ok=True)
        for img_path in val_images:
            dst_path = val_cls_dir / Path(img_path).name
            if not dst_path.exists():
                shutil.copy2(img_path, dst_path)
    
    classes = sorted(class_folders.keys())
    print(f"\nDataset prepared: {len(classes)} classes")
    return classes


# ──────────────────────────────────────────────────────────────
# 2. Data Augmentation & Loaders
# ──────────────────────────────────────────────────────────────

def get_transforms(imgsz=224):
    """Strong augmentations for training, clean for validation."""
    train_transform = transforms.Compose([
        transforms.RandomResizedCrop(imgsz, scale=(0.7, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(15),
        transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3, hue=0.1),
        transforms.RandomGrayscale(p=0.1),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225]),
    ])
    
    val_transform = transforms.Compose([
        transforms.Resize(int(imgsz * 1.15)),
        transforms.CenterCrop(imgsz),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225]),
    ])
    
    return train_transform, val_transform


def get_weighted_sampler(dataset):
    """Create a sampler that oversamples rare classes and undersamples common ones."""
    targets = [dataset.targets[i] for i in range(len(dataset))]
    class_counts = Counter(targets)
    
    # Weight = inverse of class frequency
    weights = [1.0 / class_counts[t] for t in targets]
    sampler = WeightedRandomSampler(weights, num_samples=len(weights), replacement=True)
    return sampler


# ──────────────────────────────────────────────────────────────
# 3. Model
# ──────────────────────────────────────────────────────────────

def build_model(num_classes, freeze_backbone=False):
    """
    ResNet-50 pretrained on ImageNet, fine-tuned for our classes.
    """
    model = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V2)
    
    if freeze_backbone:
        # Freeze all layers except the final FC
        for param in model.parameters():
            param.requires_grad = False
    
    # Replace the final fully connected layer
    in_features = model.fc.in_features  # 2048
    model.fc = nn.Sequential(
        nn.Dropout(0.3),
        nn.Linear(in_features, 512),
        nn.ReLU(),
        nn.Dropout(0.2),
        nn.Linear(512, num_classes)
    )
    
    return model


# ──────────────────────────────────────────────────────────────
# 4. Training Loop
# ──────────────────────────────────────────────────────────────

def train_one_epoch(model, loader, criterion, optimizer, device, epoch, total_epochs):
    model.train()
    running_loss = 0.0
    correct = 0
    total = 0
    
    pbar = tqdm(loader, desc=f"Epoch {epoch}/{total_epochs} [Train]")
    for images, labels in pbar:
        images, labels = images.to(device), labels.to(device)
        
        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()
        
        running_loss += loss.item()
        _, predicted = outputs.max(1)
        total += labels.size(0)
        correct += predicted.eq(labels).sum().item()
        
        acc = 100. * correct / total
        pbar.set_postfix(loss=f"{running_loss/total:.4f}", acc=f"{acc:.1f}%")
    
    return running_loss / len(loader), 100. * correct / total


def validate(model, loader, criterion, device, epoch, total_epochs):
    model.eval()
    running_loss = 0.0
    correct = 0
    total = 0
    
    with torch.no_grad():
        pbar = tqdm(loader, desc=f"Epoch {epoch}/{total_epochs} [Val]  ")
        for images, labels in pbar:
            images, labels = images.to(device), labels.to(device)
            
            outputs = model(images)
            loss = criterion(outputs, labels)
            
            running_loss += loss.item()
            _, predicted = outputs.max(1)
            total += labels.size(0)
            correct += predicted.eq(labels).sum().item()
            
            acc = 100. * correct / total
            pbar.set_postfix(loss=f"{running_loss/total:.4f}", acc=f"{acc:.1f}%")
    
    return running_loss / len(loader), 100. * correct / total


# ──────────────────────────────────────────────────────────────
# 5. Main
# ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Train ResNet-50 Classifier for IBVAP")
    parser.add_argument("--data", type=str,
                        default="data/cropped_classes",
                        help="Path to cropped_classes folder")
    parser.add_argument("--epochs", type=int, default=30, help="Training epochs")
    parser.add_argument("--batch", type=int, default=32, help="Batch size")
    parser.add_argument("--imgsz", type=int, default=224, help="Image size")
    parser.add_argument("--lr", type=float, default=0.001, help="Learning rate")
    parser.add_argument("--max-per-class", type=int, default=5000,
                        help="Max images per class (caps Person, Car, etc.)")
    parser.add_argument("--resume", type=str, default=None,
                        help="Path to checkpoint to resume from")
    parser.add_argument("--freeze", action="store_true",
                        help="Freeze ResNet backbone (only train classifier head)")
    
    args = parser.parse_args()
    
    # Paths
    src_dir = os.path.abspath(args.data)
    prepared_dir = os.path.join(os.path.dirname(src_dir), "classifier_dataset")
    output_dir = os.path.abspath("outputs/classifier")
    os.makedirs(output_dir, exist_ok=True)
    
    # Device
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    if device.type == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
    
    # Step 1: Prepare dataset
    classes = prepare_dataset(src_dir, prepared_dir,
                              max_per_class=args.max_per_class)
    num_classes = len(classes)
    print(f"\nTotal classes: {num_classes}")
    
    # Step 2: Create data loaders
    train_transform, val_transform = get_transforms(args.imgsz)
    
    train_dataset = datasets.ImageFolder(
        os.path.join(prepared_dir, "train"),
        transform=train_transform
    )
    val_dataset = datasets.ImageFolder(
        os.path.join(prepared_dir, "val"),
        transform=val_transform
    )
    
    # Weighted sampler for class imbalance
    sampler = get_weighted_sampler(train_dataset)
    
    train_loader = DataLoader(
        train_dataset, batch_size=args.batch,
        sampler=sampler, num_workers=2, pin_memory=True
    )
    val_loader = DataLoader(
        val_dataset, batch_size=args.batch,
        shuffle=False, num_workers=2, pin_memory=True
    )
    
    print(f"Train: {len(train_dataset)} images")
    print(f"Val:   {len(val_dataset)} images")
    
    # Save class mapping
    class_to_idx = train_dataset.class_to_idx
    idx_to_class = {v: k for k, v in class_to_idx.items()}
    
    mapping_path = os.path.join(output_dir, "class_mapping.json")
    with open(mapping_path, "w") as f:
        json.dump(idx_to_class, f, indent=2)
    print(f"Class mapping saved to {mapping_path}")
    
    # Step 3: Build model
    model = build_model(num_classes, freeze_backbone=args.freeze)
    
    start_epoch = 1
    best_acc = 0.0
    
    if args.resume:
        checkpoint = torch.load(args.resume, map_location=device)
        model.load_state_dict(checkpoint['model_state_dict'])
        start_epoch = checkpoint.get('epoch', 0) + 1
        best_acc = checkpoint.get('best_acc', 0.0)
        print(f"Resumed from epoch {start_epoch-1}, best_acc={best_acc:.1f}%")
    
    model = model.to(device)
    
    # Step 4: Loss, optimizer, scheduler
    criterion = nn.CrossEntropyLoss(label_smoothing=0.1)
    
    if args.freeze:
        # Only train the FC head
        optimizer = optim.Adam(model.fc.parameters(), lr=args.lr)
    else:
        # Different LR for backbone vs head
        backbone_params = [p for n, p in model.named_parameters()
                           if 'fc' not in n and p.requires_grad]
        head_params = list(model.fc.parameters())
        
        optimizer = optim.Adam([
            {'params': backbone_params, 'lr': args.lr * 0.1},  # Lower LR for pretrained layers
            {'params': head_params, 'lr': args.lr}             # Higher LR for new head
        ])
    
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
    
    # Step 5: Training
    print(f"\n{'='*60}")
    print("Training ResNet-50 Classifier")
    print(f"Classes: {num_classes} | Epochs: {args.epochs} | Batch: {args.batch}")
    print(f"Image Size: {args.imgsz} | LR: {args.lr} | Frozen: {args.freeze}")
    print(f"{'='*60}\n")
    
    for epoch in range(start_epoch, args.epochs + 1):
        train_loss, train_acc = train_one_epoch(
            model, train_loader, criterion, optimizer, device,
            epoch, args.epochs
        )
        val_loss, val_acc = validate(
            model, val_loader, criterion, device,
            epoch, args.epochs
        )
        
        scheduler.step()
        
        current_lr = optimizer.param_groups[-1]['lr']
        print(f"\n  → Train Loss: {train_loss:.4f} | Train Acc: {train_acc:.1f}%")
        print(f"  → Val Loss:   {val_loss:.4f} | Val Acc:   {val_acc:.1f}%")
        print(f"  → LR: {current_lr:.6f}\n")
        
        # Save checkpoint
        checkpoint = {
            'epoch': epoch,
            'model_state_dict': model.state_dict(),
            'optimizer_state_dict': optimizer.state_dict(),
            'train_loss': train_loss,
            'val_loss': val_loss,
            'val_acc': val_acc,
            'best_acc': best_acc,
            'num_classes': num_classes,
            'class_mapping': idx_to_class,
        }
        
        # Save last
        torch.save(checkpoint, os.path.join(output_dir, "last.pt"))
        
        # Save best
        if val_acc > best_acc:
            best_acc = val_acc
            checkpoint['best_acc'] = best_acc
            torch.save(checkpoint, os.path.join(output_dir, "best.pt"))
            print(f"  ★ New best model! Val Acc: {val_acc:.1f}%\n")
    
    print(f"\n{'='*60}")
    print("Training complete!")
    print(f"Best Validation Accuracy: {best_acc:.1f}%")
    print(f"Best weights: {os.path.join(output_dir, 'best.pt')}")
    print(f"Class mapping: {mapping_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
