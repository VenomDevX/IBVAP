"""train_classifier.py — stage 2 fine-grained classifier (IBVAP)

Stage 1 (YOLO) detects and crops; this classifier names what is in the crop —
F16 vs F18 vs a generic `aircraft` bucket — for the classes that have enough
unique images to support the distinction.

Reads the prepared ImageFolder tree at data/dataset/classifier/, which
scripts/build_dataset.py has already deduplicated, restructured, pruned,
folded and capped. This script does NO dataset surgery of its own. That is
deliberate: the previous version flattened, capped and split at train time,
which meant its train/val split happened AFTER collecting duplicate file
paths, so identical images landed on both sides and the reported accuracy was
partly measuring memorisation. It also carried a hardcoded skip-list for the
Military_Aircraft / Animal / Two_Wheeler aggregate folders; resolving those
structurally in the builder is what let the band-aid go away.

Fully resumable: model, optimizer, scheduler, AMP scaler and epoch are written
every epoch, so an interrupted run continues rather than restarting.

Usage:
  python scripts/train_classifier.py                      # EfficientNetV2-S
  python scripts/train_classifier.py --arch resnet50      # torchvision fallback
  python scripts/train_classifier.py --epochs 30 --resume
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, WeightedRandomSampler
from torchvision import datasets, transforms
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data" / "dataset" / "classifier"
OUT = ROOT / "models" / "classifier"
MEAN, STD = (0.485, 0.456, 0.406), (0.229, 0.224, 0.225)

# timm's in21k weights transfer better to fine-grained work than torchvision's
# in1k, which matters when the task is F16-vs-F18 rather than dog-vs-car.
DEFAULT_ARCH = "tf_efficientnetv2_s.in21k_ft_in1k"


def build_model(arch: str, n_classes: int) -> nn.Module:
    try:
        import timm

        return timm.create_model(arch, pretrained=True, num_classes=n_classes)
    except ImportError:
        from torchvision import models

        if not hasattr(models, arch):
            raise SystemExit(
                f"timm is not installed and torchvision has no '{arch}'.\n"
                f"Either  pip install timm  or pass --arch resnet50 / efficientnet_v2_s"
            ) from None
        m = getattr(models, arch)(weights="DEFAULT")
        # swap the classifier head for our class count, whatever it is called
        if hasattr(m, "fc"):
            m.fc = nn.Linear(m.fc.in_features, n_classes)
        elif hasattr(m, "classifier"):
            head = m.classifier[-1] if isinstance(m.classifier, nn.Sequential) else m.classifier
            new = nn.Linear(head.in_features, n_classes)
            if isinstance(m.classifier, nn.Sequential):
                m.classifier[-1] = new
            else:
                m.classifier = new
        else:
            raise SystemExit(f"don't know how to re-head torchvision model '{arch}'")
        return m


def loaders(size: int, batch: int, workers: int):
    if not (DATA / "train").exists():
        raise SystemExit(f"{DATA / 'train'} not found.\nRun:  python scripts/build_dataset.py")

    train_tf = transforms.Compose(
        [
            transforms.RandomResizedCrop(size, scale=(0.6, 1.0)),
            transforms.RandomHorizontalFlip(),
            transforms.ColorJitter(0.3, 0.3, 0.3, 0.05),
            transforms.ToTensor(),
            transforms.Normalize(MEAN, STD),
            transforms.RandomErasing(p=0.25),
        ]
    )
    val_tf = transforms.Compose(
        [
            transforms.Resize(int(size * 1.14)),
            transforms.CenterCrop(size),
            transforms.ToTensor(),
            transforms.Normalize(MEAN, STD),
        ]
    )

    tr = datasets.ImageFolder(DATA / "train", train_tf)
    va = datasets.ImageFolder(DATA / "val", val_tf)
    if tr.classes != va.classes:
        raise SystemExit("train and val class lists differ — rebuild the dataset")

    # The per-class cap narrows the spread but does not flatten it: Person still
    # sits at the cap while a rare aircraft type may hold only a few hundred.
    counts = [0] * len(tr.classes)
    for _, y in tr.samples:
        counts[y] += 1
    weights = [1.0 / counts[y] for _, y in tr.samples]
    sampler = WeightedRandomSampler(weights, len(weights), replacement=True)

    return (
        DataLoader(
            tr,
            batch_size=batch,
            sampler=sampler,
            num_workers=workers,
            pin_memory=True,
            drop_last=True,
            persistent_workers=workers > 0,
        ),
        DataLoader(
            va, batch_size=batch, shuffle=False, num_workers=workers, pin_memory=True, persistent_workers=workers > 0
        ),
        tr.classes,
        counts,
    )


@torch.no_grad()
def evaluate(model, loader, dev, n_classes):
    """Overall accuracy plus macro-average recall.

    Macro recall is the number that matters here: overall accuracy is dominated
    by Person and Car, so a model that ignores every rare class entirely can
    still post a flattering top-line score.
    """
    model.eval()
    correct = total = 0
    per_cls_hit = [0] * n_classes
    per_cls_tot = [0] * n_classes
    for x, y in loader:
        x, y = x.to(dev, non_blocking=True), y.to(dev, non_blocking=True)
        with torch.amp.autocast(dev, enabled=(dev == "cuda")):
            pred = model(x).argmax(1)
        correct += (pred == y).sum().item()
        total += y.numel()
        for t, p in zip(y.tolist(), pred.tolist()):
            per_cls_tot[t] += 1
            per_cls_hit[t] += t == p
    acc = correct / max(total, 1)
    recalls = [h / t for h, t in zip(per_cls_hit, per_cls_tot) if t]
    macro = sum(recalls) / max(len(recalls), 1)
    return acc, macro, per_cls_hit, per_cls_tot


def main() -> None:
    ap = argparse.ArgumentParser(description="Train the IBVAP fine-grained classifier")
    ap.add_argument("--arch", default=DEFAULT_ARCH)
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--imgsz", type=int, default=224)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--workers", type=int, default=2, help="use 0 on the Windows 'shared file mapping' error 1455")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    if dev == "cpu":
        print("WARNING: no CUDA device — this will be extremely slow.")

    tr, va, classes, counts = loaders(args.imgsz, args.batch, args.workers)
    print(f"{len(classes)} classes | train {len(tr.dataset):,} | val {len(va.dataset):,} | {dev}")
    print(f"  smallest class: {min(counts)} images   largest: {max(counts)}")

    model = build_model(args.arch, len(classes)).to(dev)
    crit = nn.CrossEntropyLoss(label_smoothing=0.1)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.05)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    scaler = torch.amp.GradScaler(dev, enabled=(dev == "cuda"))

    OUT.mkdir(parents=True, exist_ok=True)
    ckpt_path = OUT / "last.pt"
    start, best = 0, 0.0

    if args.resume and ckpt_path.exists():
        # weights_only=True: this checkpoint holds tensors, str, int and float
        # only, so there is no reason to allow arbitrary unpickling.
        ck = torch.load(ckpt_path, map_location=dev, weights_only=True)
        if ck.get("classes") != classes:
            raise SystemExit(
                "checkpoint class list differs from the dataset — the dataset was "
                "rebuilt since. Delete models/classifier/last.pt to start fresh."
            )
        model.load_state_dict(ck["model"])
        opt.load_state_dict(ck["opt"])
        sched.load_state_dict(ck["sched"])
        scaler.load_state_dict(ck["scaler"])
        start, best = ck["epoch"] + 1, ck["best"]
        print(f"resumed at epoch {start}, best macro-recall {best:.4f}")
    elif args.resume:
        print(f"--resume given but {ckpt_path} does not exist; starting fresh.")

    for ep in range(start, args.epochs):
        model.train()
        running = 0.0
        seen = 0
        for x, y in tqdm(tr, desc=f"epoch {ep + 1}/{args.epochs}", leave=False):
            x, y = x.to(dev, non_blocking=True), y.to(dev, non_blocking=True)
            opt.zero_grad(set_to_none=True)
            with torch.amp.autocast(dev, enabled=(dev == "cuda")):
                loss = crit(model(x), y)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            running += loss.item() * y.numel()
            seen += y.numel()
        sched.step()

        acc, macro, hits, tots = evaluate(model, va, dev, len(classes))
        print(f"  epoch {ep + 1:>3}: loss {running / max(seen, 1):.4f}  val acc {acc:.4f}  macro-recall {macro:.4f}")

        torch.save(
            {
                "model": model.state_dict(),
                "opt": opt.state_dict(),
                "sched": sched.state_dict(),
                "scaler": scaler.state_dict(),
                "epoch": ep,
                "best": max(best, macro),
                "classes": classes,
                "arch": args.arch,
                "imgsz": args.imgsz,
            },
            ckpt_path,
        )
        # Select on macro-recall, not accuracy: accuracy would happily pick the
        # epoch that got better at Person and worse at every military type.
        if macro > best:
            best = macro
            torch.save(
                {
                    "model": model.state_dict(),
                    "classes": classes,
                    "arch": args.arch,
                    "imgsz": args.imgsz,
                    "acc": acc,
                    "macro_recall": macro,
                },
                OUT / "ibvap_fine.pt",
            )
            (OUT / "classes.json").write_text(json.dumps(classes, indent=2), encoding="utf-8")
            print(f"    new best macro-recall {macro:.4f} -> {OUT / 'ibvap_fine.pt'}")

    acc, macro, hits, tots = evaluate(model, va, dev, len(classes))
    print(f"\nDone. best macro-recall {best:.4f}  ->  {OUT / 'ibvap_fine.pt'}")
    print("\nWorst classes by recall:")
    rows = sorted(
        ((h / t, classes[i], h, t) for i, (h, t) in enumerate(zip(hits, tots)) if t),
        key=lambda r: r[0],
    )
    for rec, name, h, t in rows[:10]:
        print(f"  {rec:6.1%}  {name:<24} {h}/{t}")


if __name__ == "__main__":
    main()
